"""render_account_context surfaces the provider firm-profile completeness snapshot."""
from app.services.help_context import render_account_context


def test_render_includes_profile_completeness_and_gaps():
    ctx = {
        "name": "Acme Engineering", "roles": ["provider"],
        "provider_profile": {
            "counts": {"capabilities": 5, "specialties": 3, "software_tools": 4,
                       "equipment": 0, "certifications": 2, "notable_projects": 1},
            "scalars": {"business_description": True, "primary_specialty": True,
                        "team_summary": False, "website": True},
            "completeness_pct": 70,
            "missing": ["equipment", "team_summary"],
            "thin": ["Notable Projects (only 1 - add several)"],
        },
    }
    out = render_account_context(ctx)
    assert "firm profile" in out.lower()
    assert "70%" in out
    assert "equipment" in out and "team summary" in out
    assert "Notable Projects" in out


def test_render_omits_profile_when_absent():
    out = render_account_context({"name": "X", "roles": ["customer"]})
    assert "firm profile" not in out.lower()
