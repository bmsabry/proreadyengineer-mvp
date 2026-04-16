"""Crawl and LLM extraction tasks for provider profile auto-fill."""

import asyncio
import json
import shutil
import tempfile
import os
from app.core.celery import celery_app


@celery_app.task(bind=True, max_retries=2, name='crawl_tasks.crawl_and_extract')
def crawl_and_extract_task(self, website_url: str, provider_id: str):
    """Crawl provider website and extract profile fields using LLM."""
    async def _run():
        tmpdir = tempfile.mkdtemp()
        try:
            # Step 1: Crawl website
            from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, DefaultMarkdownGenerator
            browser_cfg = BrowserConfig(headless=True, verbose=False)
            crawl_cfg = CrawlerRunConfig(
                markdown_generator=DefaultMarkdownGenerator(),
                cache_mode='bypass',
                storage_state=tmpdir,
            )
            all_text = []
            async with AsyncWebCrawler(config=browser_cfg) as crawler:
                result = await crawler.arun(url=website_url, config=crawl_cfg)
                if result.success:
                    all_text.append(result.markdown or result.cleaned_html or '')
                # Try up to 5 internal links
                if result.links:
                    internal = [l['href'] for l in result.links.get('internal', []) if l.get('href', '').startswith('http')][:4]
                    for link in internal:
                        try:
                            sub = await crawler.arun(url=link, config=crawl_cfg)
                            if sub.success:
                                all_text.append(sub.markdown or sub.cleaned_html or '')
                        except Exception:
                            pass

            raw_text = '\n\n'.join(all_text)[:80000]  # Limit to 80k chars
            return raw_text
        finally:
            # IMMEDIATELY delete all crawl files
            shutil.rmtree(tmpdir, ignore_errors=True)

    async def _extract(raw_text: str):
        from app.services.config_service import RuntimeConfig
        cfg = RuntimeConfig.get()
        api_key = cfg.get('DOC_LLM_API_KEY') or cfg.get('OPENAI_API_KEY')
        api_base = cfg.get('DOC_LLM_API_BASE') or cfg.get('OPENAI_API_BASE') or 'https://api.openai.com/v1'
        model = cfg.get('DOC_LLM_MODEL') or cfg.get('OPENAI_LLM_MODEL') or 'gpt-4o'

        prompt = f"""You are extracting structured data from an engineering firm's website content.

Website content:
{raw_text}

Extract and return a JSON object with ONLY these fields (use null if not found):
{{
  "firm_name": "Legal firm name",
  "name": "Display name",
  "business_description": "2-4 sentence description of what the firm does",
  "primary_specialty": "Single primary engineering specialty",
  "secondary_specialties": ["list", "of", "secondary", "specialties"],
  "capabilities": ["list", "of", "specific", "engineering", "capabilities"],
  "specialties": ["list", "of", "specialties"],
  "software_tools": ["list", "of", "software", "tools", "used"],
  "proven_experience_notable_projects": ["For each project or case study found, write EXACTLY ONE sentence that captures: (1) what engineering service was performed, (2) the method or approach used, (3) the outcome or purpose. Be factual and technical. Each item is one project."],
  "proven_experience_case_studies": ["list", "of", "case", "study", "summaries"],
  "website": "firm website URL",
  "phone": "phone number",
  "email_addresses": ["list@of.emails"],
  "address": "street address",
  "city": "city",
  "state": "state",
  "postal_code": "postal code",
  "certifications": ["list", "of", "certifications"],
  "notable_clients": ["list", "of", "notable", "clients"],
  "equipment": ["list", "of", "equipment"],
  "team_members": ["list", "of", "key", "team", "members"],
  "team_summary": "brief team summary",
  "projects": "general project portfolio description"
}}

IMPORTANT for proven_experience_notable_projects: Each entry must be exactly ONE sentence per project capturing what was done, how, and why. Return ONLY valid JSON."""

        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=api_key, base_url=api_base)
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        content = response.choices[0].message.content
        return json.loads(content)

    async def _main():
        raw_text = await _run()
        if not raw_text.strip():
            return {"status": "failed", "error": "No content extracted from website"}
        extracted = await _extract(raw_text)
        return {"status": "done", "data": extracted}

    try:
        result = asyncio.run(_main())
        return result
    except Exception as exc:
        raise self.retry(exc=exc, countdown=10)
