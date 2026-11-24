"""Skill normalisation."""

from __future__ import annotations

from careergraph.skills import SkillNormalizer


def test_aliases_map_to_canonical(skills: SkillNormalizer) -> None:
    assert skills.normalize("Py") == "python"
    assert skills.normalize("  K8s ") == "kubernetes"
    assert skills.normalize("Unknown Thing") == "unknown thing"
    assert skills.normalize_all(["torch", "PyTorch", "sklearn"]) == ["pytorch", "scikit-learn"]


def test_find_in_text_whole_words_and_multiword(skills: SkillNormalizer) -> None:
    text = "We use PyTorch on k8s, Retrieval-Augmented Generation and C++; scikit learn too."
    assert skills.find_in_text(text) == ["pytorch", "kubernetes", "rag", "c++", "scikit-learn"]


def test_short_terms_need_capitalisation(skills: SkillNormalizer) -> None:
    assert "go" not in skills.find_in_text("You will go far with us.")
    assert "go" in skills.find_in_text("Services written in Go.")
    assert "machine learning" in skills.find_in_text("Strong ML background.")


def test_related_is_one_hop(skills: SkillNormalizer) -> None:
    assert skills.related("torch") == {"tensorflow", "jax"}
    assert skills.related("nonexistent") == set()
