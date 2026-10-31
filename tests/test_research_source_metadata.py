import pytest
from scripts.research.analyze_gap_bounds import analyze
from scripts.research.summarize_post_stop import summarize as post
from scripts.research.summarize_stabilized_arrival import summarize as stabilized
from scripts.research.summarize_velocity_retry import summarize as retry
from test_analyze_gap_bounds import sample as gap_sample
from test_summarize_post_stop import fixture as post_sample
from test_summarize_stabilized_arrival import sample as stabilized_sample


@pytest.mark.parametrize("fn,factory", [(analyze, gap_sample), (lambda d: post(d, .25), post_sample),
    (lambda d: stabilized(d, .25), stabilized_sample), (lambda d: retry(d, .25), stabilized_sample)])
def test_all_analyzers_reject_inconsistent_source_maps(fn, factory):
    data = factory()
    data["source_sha256_after"]["source.py"] = "b" * 64
    with pytest.raises(ValueError):
        fn(data)
