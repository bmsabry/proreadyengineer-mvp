"""Search service for provider matching using AI embeddings."""

import json
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from openai import AsyncOpenAI

from app.core.config import settings
from app.models.provider import Provider
from app.models.search import SearchRequest
from app.schemas.search import SearchQuery, SearchResult, ProviderMatch


class SearchService:
    """Service for AI-powered provider search."""

    def __init__(self):
        """Initialize OpenAI-compatible client."""
        client_kwargs = {
            "api_key": settings.OPENAI_API_KEY or "dummy-key",
        }
        
        # Support custom base URL (e.g., DeepInfra, other providers)
        if settings.OPENAI_API_BASE:
            client_kwargs["base_url"] = settings.OPENAI_API_BASE
            
        self.client = AsyncOpenAI(**client_kwargs)
        self.embedding_model = settings.OPENAI_EMBEDDING_MODEL
        self.llm_model = settings.OPENAI_LLM_MODEL

    async def extract_search_intent(
        self, query_text: str, document_text: Optional[str] = None
    ) -> Dict[str, Any]:
        """Use LLM to extract structured intent from search query."""
        combined_text = query_text
        if document_text:
            combined_text += f"\n\nDocument content:\n{document_text[:4000]}"

        prompt = f"""
        Analyze this engineering services search query and extract structured information.
        
        Query: {combined_text}
        
        Return ONLY a JSON object with these fields:
        - requires_engineering: 1 if engineering services needed, 0 otherwise
        - requires_mechanical: 1 if mechanical engineering focus, 0 otherwise
        - requires_software: 1 if software/simulation tools mentioned, 0 otherwise
        - software_mentioned: list of software tools mentioned (e.g., ["ANSYS", "SolidWorks"])
        - inferred_specialty: primary engineering specialty inferred (string)
        - capabilities_needed: list of required capabilities
        - tollgate_phases: list of tollgate phases mentioned (TG0, TG1, TG3, TG4, TG6)
        
        Return valid JSON only, no markdown formatting.
        """

        try:
            response = await self.client.chat.completions.create(
                model=self.llm_model,
                messages=[
                    {"role": "system", "content": "You are an engineering services analyzer. Return only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=500
            )

            content = response.choices[0].message.content.strip()
            
            # Clean up markdown formatting if present
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            parsed = json.loads(content)
            return parsed

        except Exception as e:
            # Fallback: return basic structure
            return {
                "requires_engineering": 1,
                "requires_mechanical": 0,
                "requires_software": 0,
                "software_mentioned": [],
                "inferred_specialty": "general engineering",
                "capabilities_needed": [],
                "tollgate_phases": []
            }

    async def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding vector for text."""
        # Truncate if too long
        text = text[:8000]
        
        response = await self.client.embeddings.create(
            model=self.embedding_model,
            input=text
        )
        return response.data[0].embedding

    async def search_providers(
        self,
        db: AsyncSession,
        search_query: SearchQuery,
        user_id: Optional[int] = None,
        ip_address: Optional[str] = None
    ) -> SearchResult:
        """Execute AI-powered provider search."""
        
        # Combine query with document text if provided
        combined_text = search_query.query
        document_text = None
        if search_query.document_text:
            document_text = search_query.document_text
            combined_text += " " + document_text[:1000]

        # Extract structured intent using LLM
        intent = await self.extract_search_intent(
            search_query.query,
            document_text
        )

        # Generate embedding for vector similarity search
        query_embedding = await self.generate_embedding(combined_text)

        # Build base query with vector similarity
        embedding_str = f"[{','.join(str(x) for x in query_embedding)}]"
        
        # Query for providers with vector similarity
        # Using pgvector cosine similarity
        stmt = select(
            Provider,
            (1 - Provider.embedding.cosine_distance(embedding_str)).label("similarity")
        ).where(
            Provider.embedding.isnot(None)
        ).order_by(
            Provider.embedding.cosine_distance(embedding_str)
        ).limit(50)

        result = await db.execute(stmt)
        rows = result.all()

        # Score and rank providers
        matches = []
        for idx, (provider, similarity) in enumerate(rows):
            score = self._calculate_score(provider, intent, similarity)
            
            match = ProviderMatch(
                provider_id=provider.id,
                name=provider.name,
                tier=provider.tier,
                primary_specialty=provider.primary_specialty,
                city=provider.city,
                state=provider.state,
                composite_score=score["total"],
                specialty_score=score["specialty"],
                capabilities_score=score["capabilities"],
                tier_score=score["tier"],
                explanation=score["explanation"]
            )
            matches.append(match)

        # Sort by composite score and take top 5
        matches.sort(key=lambda x: x.composite_score, reverse=True)
        top_matches = matches[:5]

        # Create search request record
        search_request = SearchRequest(
            user_id=user_id,
            ip_address=ip_address,
            raw_query_text=search_query.query,
            extracted_document_text=document_text[:2000] if document_text else None,
            normalized_query_text=combined_text[:1000],
            llm_structured_output=intent,
            embedding_model=self.embedding_model,
            embedding_version="1.0",
            llm_model=self.llm_model,
            search_status="completed",
            fallback_reason=None
        )
        db.add(search_request)
        await db.commit()

        return SearchResult(
            matches=top_matches,
            total_matches=len(matches),
            query_id=search_request.id,
            query_text=search_query.query
        )

    def _calculate_score(
        self,
        provider: Provider,
        intent: Dict[str, Any],
        similarity: float
    ) -> Dict[str, Any]:
        """Calculate 100-point composite score for a provider match."""
        
        # Base similarity score (0-50 points for capabilities match)
        capabilities_score = min(50, int(similarity * 50))
        
        # Specialty match (0-25 points)
        specialty_score = 0
        inferred_specialty = intent.get("inferred_specialty", "").lower()
        if provider.primary_specialty and inferred_specialty:
            if inferred_specialty in provider.primary_specialty.lower():
                specialty_score = 25
            elif provider.secondary_specialties:
                secondary_match = any(
                    inferred_specialty in s.lower()
                    for s in (provider.secondary_specialties or [])
                )
                if secondary_match:
                    specialty_score = 20

        # Tier multiplier (5-25 points)
        tier_scores = {"A": 25, "B": 20, "C": 15, "D": 10, "E": 5}
        tier_score = tier_scores.get(provider.tier, 5)

        # Software match bonus (up to 10 bonus points)
        software_bonus = 0
        mentioned_software = intent.get("software_mentioned", [])
        if mentioned_software and provider.software_tools:
            matches = sum(
                1 for sw in mentioned_software
                if any(sw.lower() in pt.lower() for pt in provider.software_tools)
            )
            software_bonus = min(10, matches * 3)

        total = min(100, capabilities_score + specialty_score + tier_score + software_bonus)

        # Generate explanation
        explanation_parts = []
        if specialty_score >= 20:
            explanation_parts.append(f"Strong specialty match in {provider.primary_specialty}")
        if capabilities_score >= 35:
            explanation_parts.append("High capability alignment")
        if software_bonus > 0:
            explanation_parts.append(f"Uses relevant software tools")
        explanation_parts.append(f"Tier {provider.tier} provider")

        return {
            "total": total,
            "specialty": specialty_score,
            "capabilities": capabilities_score,
            "tier": tier_score,
            "software_bonus": software_bonus,
            "explanation": "; ".join(explanation_parts) if explanation_parts else "General match"
        }

    async def generate_provider_embedding(
        self,
        provider: Provider
    ) -> List[float]:
        """Generate embedding for a provider's business description."""
        # Combine relevant fields for embedding
        text_parts = [
            provider.name or "",
            provider.primary_specialty or "",
            provider.business_description or "",
            " ".join(provider.capabilities or []),
            " ".join(provider.specialties or []),
        ]
        text = " ".join(filter(None, text_parts))
        
        return await self.generate_embedding(text)


# Global instance
search_service = SearchService()
