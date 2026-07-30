from app.schemas import SampleRequest


def test_sample_request_accepts_popularity_range():
    body = SampleRequest(popularity_min=30, popularity_max=50, limit=10)
    assert body.popularity_min == 30
    assert body.popularity_max == 50


def test_sample_request_rejects_popularity_out_of_bounds():
    try:
        SampleRequest(popularity_min=-1)
        assert False, "expected validation error"
    except Exception:
        pass
    try:
        SampleRequest(popularity_max=101)
        assert False, "expected validation error"
    except Exception:
        pass
