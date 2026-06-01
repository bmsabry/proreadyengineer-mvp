"""Unit tests for the assistant's profile-update merge logic + allowlist placement."""
from app.services import help_actions as ha


def test_update_profile_action_allowlisted_not_forbidden():
    assert "update_profile_from_docs" in ha.SAFE_ACTIONS
    assert "update_profile_from_docs" in ha.ALL_ACTIONS
    assert "update_profile_from_docs" not in ha.FORBIDDEN_ACTIONS


def test_merge_lists_additive_dedup_case_insensitive():
    existing = {"capabilities": ["FEA", "HVAC design"]}
    extracted = {"capabilities": ["fea", "CFD", "HVAC Design", "CFD"]}
    merged, changed = ha._merge_profile_fields(existing, extracted)
    assert "capabilities" in changed
    # existing kept first; only genuinely-new added (case-insensitive); deduped
    assert merged["capabilities"] == ["FEA", "HVAC design", "CFD"]


def test_merge_no_change_when_extracted_is_subset():
    merged, changed = ha._merge_profile_fields(
        {"specialties": ["oil & gas"]}, {"specialties": ["Oil & Gas"]}
    )
    assert "specialties" not in changed and merged == {}


def test_merge_notable_projects_capped_at_30():
    existing = {"proven_experience_notable_projects": ["p%d" % i for i in range(28)]}
    extracted = {"proven_experience_notable_projects": ["n%d" % i for i in range(10)]}
    merged, changed = ha._merge_profile_fields(existing, extracted)
    assert len(merged["proven_experience_notable_projects"]) == 30


def test_merge_scalar_fills_only_when_empty():
    m, c = ha._merge_profile_fields({"team_summary": ""}, {"team_summary": "Great team."})
    assert m["team_summary"] == "Great team." and "team_summary" in c
    m2, c2 = ha._merge_profile_fields({"team_summary": "Existing."}, {"team_summary": "New."})
    assert "team_summary" not in c2


def test_merge_ignores_empty_extracted_lists():
    m, c = ha._merge_profile_fields({"capabilities": ["FEA"]}, {"capabilities": []})
    assert c == set() and m == {}


def test_merge_never_removes_existing():
    existing = {"software_tools": ["SolidWorks", "ANSYS"]}
    extracted = {"software_tools": ["Creo"]}
    merged, changed = ha._merge_profile_fields(existing, extracted)
    assert merged["software_tools"][:2] == ["SolidWorks", "ANSYS"]
    assert "Creo" in merged["software_tools"]


def test_validate_profile_updates_sanitizes_to_known_fields():
    raw = {
        "capabilities": ["CFD analysis", "  ", 5],
        "team_summary": "A 6-person FEA team.",
        "evil_field": ["drop table"],
        "primary_specialty": "   ",
    }
    out = ha._validate_profile_updates(raw)
    assert out["capabilities"] == ["CFD analysis", "5"]
    assert out["team_summary"] == "A 6-person FEA team."
    assert "evil_field" not in out
    assert "primary_specialty" not in out  # blank dropped


def test_validate_profile_updates_rejects_non_dict():
    assert ha._validate_profile_updates(None) == {}
    assert ha._validate_profile_updates(["x"]) == {}


def test_update_profile_from_chat_allowlisted():
    assert "update_profile_from_chat" in ha.SAFE_ACTIONS
    assert "update_profile_from_chat" not in ha.FORBIDDEN_ACTIONS
