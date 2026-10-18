"""Offline fakes for Jev and Claude so the full pipeline can be exercised with zero API calls.
Usage: PIPELINE_LEDGER=state/mock_ledger.db python -m tests.mock_models <pipeline.run args>"""
import json, re, sys, types, uuid

class _A:  # answer
    def __init__(self, choice=None, score=None, confidence=0.9): self.choice, self.score, self.confidence = choice, score, confidence

def _fake_system_one(self, state, questions, **kw):
    t = state.lower()
    if "subtopic" in questions:
        opts = list(questions["subtopic"].criteria) if hasattr(questions["subtopic"], "criteria") else ["general"]
        ans = {"subtopic": _A(opts[0])}
    else:
        neg = any(w in t for w in ("bad", "hate", "worst", "ads", "premium", "can't", "cant", "not "))
        topic = "billing" if "premium" in t else "usability" if "ad" in t else "playback" if "play" in t else "other"
        ans = {"topic": _A(topic), "intent": _A("complaint" if neg else "praise"),
               "severity": _A("3" if neg else "1"), "sentiment": _A(score=1.0 if neg else 3.5)}
    r = types.SimpleNamespace(model="jev-mock-0", answers=ans,
                              usage=types.SimpleNamespace(input_tokens=1170, output_tokens=196),
                              raw_http_response=types.SimpleNamespace(headers={"x-typesafe-request-id": "mock-" + uuid.uuid4().hex}))
    return r

class _Msg:
    def __init__(self, text, model):
        self.content = [types.SimpleNamespace(type="text", text=text)]
        self.stop_reason, self.model, self.id, self._request_id = "end_turn", model, "msg_mock", "req_mock_" + uuid.uuid4().hex
        self.usage = types.SimpleNamespace(input_tokens=2000, output_tokens=300, cache_read_input_tokens=0, cache_creation_input_tokens=0)

def _fake_create(**p):
    user = p["messages"][0]["content"]
    if p["model"].startswith("claude-haiku") and "Label these reviews" in user:
        items = json.loads(user.split("\n", 1)[1])
        return _Msg(json.dumps({"labels": [{"n": it["n"], "topic": "other", "intent": "praise", "severity": 1, "sentiment": 0.5} for it in items]}), p["model"])
    if p["model"].startswith("claude-haiku"):
        pack = json.loads(user.split("\n", 1)[1])
        return _Msg(json.dumps({"topics": [{"topic": t, "subtopics": [{"id": "mock_issue", "name": "Mock", "description": "mock"}]} for t in pack]}), p["model"])
    pack = json.loads(user.split("\n", 1)[1])
    top = pack["top_issues"][0]
    q = top["representative_quotes"][0]
    md = f"## Recommendation\nFocus on {top['issue_id']} ({top['complaint_count']} complaints [C1]). Example {q['review_id']}."
    return _Msg(json.dumps({"recommended_issue_id": top["issue_id"], "memo_markdown": md,
                            "claims": [{"claim_id": "C1", "issue_id": top["issue_id"], "metric": "complaint_count", "value": top["complaint_count"]}],
                            "cited_reviews": [{"review_id": q["review_id"], "issue_id": top["issue_id"]}]}), p["model"])

def install():
    import typesafe_sdk
    typesafe_sdk.TypeSafeClient.system_one = _fake_system_one
    import pipeline.claude_call as cc
    cc._client = types.SimpleNamespace(messages=types.SimpleNamespace(create=_fake_create))

if __name__ == "__main__":
    install()
    from pipeline import run
    sys.argv = ["pipeline.run"] + sys.argv[1:]
    run.main()
