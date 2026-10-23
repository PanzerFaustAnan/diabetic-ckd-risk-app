from app.guidance import build_guidance


def base(**kw):
    p = dict(sex=0, job=1, fam=0, dy=5, age=50, bmi=23, diet=1, med=1, ins=0, htn=0, hd=0, sleep=1, water=1, smoke=0, zarda=0,
             walk=1, urin=1, uti=0, pk=0, cal=1400)
    p.update(kw)
    return p


def ids(p, tier="Low"):
    return {g["id"] for g in build_guidance(p, tier)}


def test_healthy_profile_gets_only_the_universal_items():
    assert ids(base()) == {"kidney-check", "bp", "diabetes-meds", "glucose"}


def test_rules_trigger_on_inputs():
    assert "smoking" in ids(base(smoke=1))
    assert "painkillers" in ids(base(pk=1))
    assert "fluids" in ids(base(water=0))
    assert "urinary" in ids(base(uti=1)) and "urinary" in ids(base(urin=0))
    assert "weight" in ids(base(bmi=27)) and "weight-low" in ids(base(bmi=17))


def test_guidance_does_not_depend_on_model_direction():
    # walking and hypertension contradict the model; guidance must still follow guidelines
    assert "activity" in ids(base(walk=0))
    assert "activity" not in ids(base(walk=1))
    assert any("Keep blood pressure" in g["title"] for g in build_guidance(base(htn=1), "Low"))


def test_high_tier_check_is_prioritised_and_first():
    g = build_guidance(base(), "High")
    assert g[0]["id"] == "kidney-check" and g[0]["priority"] == "high"
    assert "not a diagnosis" in g[0]["text"]


def test_no_item_makes_a_diagnostic_claim():
    for p in (base(), base(smoke=1, pk=1, uti=1, water=0, walk=0, diet=0, bmi=30, sleep=0, hd=1, htn=1)):
        for g in build_guidance(p, "High"):
            text = g["text"].lower()
            for phrase in ("you have ckd", "you have kidney", "you have chronic", "you are diagnosed", "you will develop"):
                assert phrase not in text
