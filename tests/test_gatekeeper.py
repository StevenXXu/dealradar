"""Tests for src/reasoner/gatekeeper.py.

Covers the three building blocks independently (GarbageNameFilter,
AlreadyEnrichedFilter, FilterChain) plus the default_chain factory.
The reasoner pipeline integration is tested in test_reasoner_pipeline.py.
"""
import json

import pytest

from src.reasoner.gatekeeper import (
    AlreadyEnrichedFilter,
    FilterChain,
    GarbageNameFilter,
    default_chain,
)


# ─── GarbageNameFilter ───────────────────────────────────────────────


class TestGarbageNameFilter:
    @pytest.fixture
    def f(self) -> GarbageNameFilter:
        return GarbageNameFilter()

    def test_passes_real_company_name(self, f):
        assert f.check({"company_name": "Canvas"}) == "pass"
        assert f.check({"company_name": "Stables Money"}) == "pass"
        assert f.check({"company_name": "PlasmaLeap"}) == "pass"

    @pytest.mark.parametrize(
        "garbage",
        [
            "Website",
            "Read More",
            "Learn More",
            "View More",
            "Visit Website",
            "About",
            "Contact",
            "Portfolio",
            "Companies",
            "Click here",
            "Menu",
        ],
    )
    def test_drops_known_link_text_as_company_name(self, f, garbage):
        assert f.check({"company_name": garbage}) == "skip:garbage_name"

    def test_match_is_case_insensitive(self, f):
        assert f.check({"company_name": "WEBSITE"}) == "skip:garbage_name"
        assert f.check({"company_name": "website"}) == "skip:garbage_name"
        assert f.check({"company_name": "  Website  "}) == "skip:garbage_name"

    def test_drops_empty_or_missing_name(self, f):
        assert f.check({"company_name": ""}) == "skip:garbage_name:empty"
        assert f.check({"company_name": "   "}) == "skip:garbage_name:empty"
        assert f.check({"company_name": None}) == "skip:garbage_name:empty"
        assert f.check({}) == "skip:garbage_name:empty"

    def test_drops_very_short_names(self, f):
        assert f.check({"company_name": "A"}) == "skip:garbage_name:too_short"
        assert f.check({"company_name": "Ai"}) == "skip:garbage_name:too_short"

    def test_passes_names_that_contain_garbage_words(self, f):
        # 'About Face' or 'News Corp' are real names — substring matching
        # would be wrong. Only exact match should trigger.
        assert f.check({"company_name": "About Face"}) == "pass"
        assert f.check({"company_name": "News Corp"}) == "pass"
        assert f.check({"company_name": "Read AI"}) == "pass"


# ─── AlreadyEnrichedFilter ───────────────────────────────────────────


class TestAlreadyEnrichedFilter:
    def test_passes_when_enriched_file_missing(self, tmp_path):
        f = AlreadyEnrichedFilter(tmp_path / "does_not_exist.json")
        assert f.check({"domain": "https://canvas.co"}) == "pass"

    def test_passes_when_enriched_file_empty_list(self, tmp_path):
        path = tmp_path / "enriched.json"
        path.write_text("[]")
        f = AlreadyEnrichedFilter(path)
        assert f.check({"domain": "https://canvas.co"}) == "pass"

    def test_passes_when_enriched_file_malformed(self, tmp_path):
        # Treat malformed JSON as 'nothing seen' so a corrupt cache
        # never blocks the pipeline.
        path = tmp_path / "enriched.json"
        path.write_text("not json {{{")
        f = AlreadyEnrichedFilter(path)
        assert f.check({"domain": "https://canvas.co"}) == "pass"

    def test_drops_domain_present_in_enriched(self, tmp_path):
        path = tmp_path / "enriched.json"
        path.write_text(
            json.dumps([{"domain": "https://canvas.co", "company_name": "Canvas"}])
        )
        f = AlreadyEnrichedFilter(path)
        assert f.check({"domain": "https://canvas.co"}) == "skip:already_enriched"

    def test_passes_domain_not_in_enriched(self, tmp_path):
        path = tmp_path / "enriched.json"
        path.write_text(json.dumps([{"domain": "https://canvas.co"}]))
        f = AlreadyEnrichedFilter(path)
        assert f.check({"domain": "https://newco.io"}) == "pass"

    @pytest.mark.parametrize(
        "enriched_form,incoming_form",
        [
            ("https://canvas.co", "http://canvas.co"),
            ("https://canvas.co", "https://www.canvas.co"),
            ("https://www.canvas.co/", "canvas.co"),
            ("HTTPS://CANVAS.CO", "canvas.co"),
            ("canvas.co", "https://canvas.co/"),
        ],
    )
    def test_domain_normalization(self, tmp_path, enriched_form, incoming_form):
        # Different surface forms of the same domain should compare equal,
        # otherwise we re-pay LLM costs for trivial URL variants.
        path = tmp_path / "enriched.json"
        path.write_text(json.dumps([{"domain": enriched_form}]))
        f = AlreadyEnrichedFilter(path)
        assert f.check({"domain": incoming_form}) == "skip:already_enriched"

    def test_passes_when_company_has_no_domain(self, tmp_path):
        path = tmp_path / "enriched.json"
        path.write_text(json.dumps([{"domain": "https://canvas.co"}]))
        f = AlreadyEnrichedFilter(path)
        # No domain to compare → can't be already-enriched, must pass
        assert f.check({"company_name": "Mystery"}) == "pass"
        assert f.check({"domain": None}) == "pass"
        assert f.check({"domain": ""}) == "pass"

    def test_ignores_non_dict_entries_in_enriched(self, tmp_path):
        path = tmp_path / "enriched.json"
        path.write_text(json.dumps(["bare string", 42, None]))
        f = AlreadyEnrichedFilter(path)
        # Should not crash, just treat all as unseen
        assert f.check({"domain": "https://canvas.co"}) == "pass"


# ─── FilterChain ─────────────────────────────────────────────────────


class _AlwaysPass:
    name = "always_pass"
    calls = 0

    def check(self, company):
        type(self).calls += 1
        return "pass"


class _AlwaysSkip:
    name = "always_skip"
    calls = 0

    def check(self, company):
        type(self).calls += 1
        return f"skip:{self.name}"


class TestFilterChain:
    def test_empty_chain_passes_everything(self):
        chain = FilterChain()
        passers, skippers = chain.apply([{"company_name": "Anything"}])
        assert len(passers) == 1
        assert len(skippers) == 0

    def test_single_filter_skip_routes_to_skippers(self):
        chain = FilterChain().add(_AlwaysSkip())
        passers, skippers = chain.apply([{"company_name": "X"}])
        assert passers == []
        assert len(skippers) == 1
        assert skippers[0]["_gatekeeper_skip"] == "skip:always_skip"

    def test_evaluate_short_circuits_on_first_skip(self):
        # Reset counters
        _AlwaysSkip.calls = 0
        _AlwaysPass.calls = 0
        chain = FilterChain().add(_AlwaysSkip()).add(_AlwaysPass())
        chain.evaluate({"company_name": "X"})
        # First filter rejects → second should not be invoked
        assert _AlwaysSkip.calls == 1
        assert _AlwaysPass.calls == 0

    def test_stats_track_per_reason_counts(self):
        chain = FilterChain().add(GarbageNameFilter())
        passers, skippers = chain.apply(
            [
                {"company_name": "Canvas"},
                {"company_name": "Stables Money"},
                {"company_name": "Website"},
                {"company_name": "Read More"},
                {"company_name": ""},
            ]
        )
        assert len(passers) == 2
        assert len(skippers) == 3
        assert chain.stats["total"] == 5
        assert chain.stats["passed"] == 2
        assert chain.stats["skipped"]["skip:garbage_name"] == 2
        assert chain.stats["skipped"]["skip:garbage_name:empty"] == 1

    def test_stats_reset_between_runs(self):
        chain = FilterChain().add(GarbageNameFilter())
        chain.apply([{"company_name": "Website"}])
        chain.apply([{"company_name": "Canvas"}])
        # Second run's stats should not carry the first run's count
        assert chain.stats["total"] == 1
        assert chain.stats["passed"] == 1
        assert "skip:garbage_name" not in chain.stats["skipped"]

    def test_skipped_entry_preserves_original_fields(self):
        chain = FilterChain().add(GarbageNameFilter())
        _, skippers = chain.apply(
            [{"company_name": "Website", "domain": "https://x.com", "vc_source": "VC"}]
        )
        assert skippers[0]["domain"] == "https://x.com"
        assert skippers[0]["vc_source"] == "VC"
        assert skippers[0]["company_name"] == "Website"
        assert skippers[0]["_gatekeeper_skip"] == "skip:garbage_name"

    def test_format_summary_handles_empty_input(self):
        chain = FilterChain()
        chain.apply([])
        assert "no companies" in chain.format_summary().lower()

    def test_format_summary_reports_skip_reasons(self):
        chain = FilterChain().add(GarbageNameFilter())
        chain.apply(
            [
                {"company_name": "Canvas"},
                {"company_name": "Website"},
                {"company_name": "Read More"},
            ]
        )
        summary = chain.format_summary()
        assert "Passed to LLM" in summary
        assert "skip:garbage_name" in summary
        # Counts should appear
        assert "1 (33.3%)" in summary or "1 (33%)" in summary


# ─── default_chain ───────────────────────────────────────────────────


class TestDefaultChain:
    def test_default_chain_has_both_filters(self, tmp_path):
        chain = default_chain(tmp_path / "enriched.json")
        names = [type(f).__name__ for f in chain.filters]
        assert "GarbageNameFilter" in names
        assert "AlreadyEnrichedFilter" in names

    def test_default_chain_garbage_filter_runs_first(self, tmp_path):
        # Order matters: garbage filter is pure-Python and instant,
        # already_enriched does file IO. Garbage first lets us skip
        # the IO check for obviously-bad rows.
        chain = default_chain(tmp_path / "enriched.json")
        assert isinstance(chain.filters[0], GarbageNameFilter)
        assert isinstance(chain.filters[1], AlreadyEnrichedFilter)

    def test_default_chain_end_to_end(self, tmp_path):
        enriched = tmp_path / "enriched.json"
        enriched.write_text(json.dumps([{"domain": "https://canvas.co"}]))
        chain = default_chain(enriched)
        passers, skippers = chain.apply(
            [
                {"company_name": "Canvas", "domain": "https://canvas.co"},     # already enriched
                {"company_name": "Website", "domain": "https://www.x.com"},    # garbage
                {"company_name": "Newco", "domain": "https://newco.io"},       # passes
            ]
        )
        assert len(passers) == 1
        assert passers[0]["company_name"] == "Newco"
        assert len(skippers) == 2
        skip_reasons = sorted(s["_gatekeeper_skip"] for s in skippers)
        assert skip_reasons == ["skip:already_enriched", "skip:garbage_name"]
