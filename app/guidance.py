"""General health guidance layer.

DESIGN RULE (decided in the project notes): this layer is INDEPENDENT of the statistical model.
* The model layer answers "how does this profile compare with the study patients?" (descriptive, from the data).
* This layer answers "what do general diabetes/kidney guidelines say for someone who reports X?" (from public guidelines).
Why separate? SHAP explains the model, not the world. In this dataset two features (regular walking, hypertension) move
the score OPPOSITE to clinical knowledge, so advice generated from the model would sometimes be wrong. Rules written
from guidelines never are.

Every rule is a plain, readable `if`, so a clinician can review the wording line by line. STATUS says honestly that the
text has not yet been clinician-reviewed; change it only after that has happened.
"""
from __future__ import annotations

STATUS = ("Draft general information based on public guidelines. It is not personalised medical advice, it does not use your risk "
          "score, and it has not yet been reviewed by a clinician.")

SOURCES = [
    "American Diabetes Association, Standards of Care in Diabetes: Chronic Kidney Disease and Risk Management (kidney screening at least yearly with eGFR and urine albumin-to-creatinine ratio)",
    "KDIGO 2022 Clinical Practice Guideline for Diabetes Management in Chronic Kidney Disease",
    "National Kidney Foundation: Kidney Health Evaluation for people with diabetes (eGFR + uACR; avoid prolonged NSAID use)",
    "NICE guideline NG203: Chronic kidney disease, assessment and management (annual eGFR in long-term NSAID users)",
]


def _item(id_, topic, title, text, high=False):
    return dict(id=id_, topic=topic, title=title, text=text, priority="high" if high else "normal")


def build_guidance(p: dict, tier: str) -> list[dict]:
    g: list[dict] = []

    # --- kidney check-ups: always present, more urgent wording for the High tier
    if tier == "High":
        g.append(_item("kidney-check", "Check-ups", "Consider a kidney check soon",
                       "Your answers resemble those of study patients who were diagnosed with chronic kidney disease (CKD). This is not a diagnosis. "
                       "If you have not had a kidney check in the last year, ask your doctor for two simple tests: a blood test (eGFR) and a urine test "
                       "(albumin-to-creatinine ratio). CKD is often silent in its early stages, so these tests are how it is found.", high=True))
    else:
        g.append(_item("kidney-check", "Check-ups", "Get your kidneys checked every year",
                       "Diabetes guidelines recommend checking kidney function at least once a year with a blood test (eGFR) and a urine test "
                       "(albumin-to-creatinine ratio). CKD is often silent in its early stages, so these tests are how it is found."))

    # --- urinary symptoms
    if p["uti"] == 1 or p["urin"] == 0:
        g.append(_item("urinary", "Urinary health", "See a doctor about urinary problems",
                       "Urinary infections, pain, or difficulty passing urine should be checked by a doctor promptly. Repeated or untreated problems "
                       "can affect the kidneys.", high=True))

    # --- tobacco
    if p["smoke"] == 1:
        g.append(_item("smoking", "Tobacco", "Quitting smoking protects your kidneys and heart",
                       "In people with diabetes, smoking is linked to faster kidney damage and to heart disease. Quitting is one of the most effective "
                       "steps you can take. Your doctor or pharmacist can suggest support such as counselling or medicines."))
    if p["zarda"] == 1:
        g.append(_item("zarda", "Tobacco", "Chewing tobacco (zarda) is harmful",
                       "Chewing tobacco products carry serious health risks, including heart disease and cancers of the mouth. Ask your doctor about "
                       "support to quit."))

    # --- medicines
    if p["pk"] == 1:
        g.append(_item("painkillers", "Medicines", "Be careful with regular pain-killers",
                       "Regular use of anti-inflammatory pain-killers (NSAIDs such as ibuprofen, diclofenac or naproxen) can harm the kidneys, and the risk "
                       "is higher in diabetes. Do not stop any medicine your doctor prescribed. Ask your doctor or pharmacist whether a safer option exists, "
                       "and have your kidney function checked if you use them long-term."))
    if p["ins"] == 1 or p["med"] == 1:
        g.append(_item("diabetes-meds", "Medicines", "Take diabetes medicines exactly as prescribed",
                       "Do not change doses on your own. Some diabetes medicines need adjusting if kidney function falls, which is one more reason for "
                       "yearly kidney tests."))

    # --- fluids (neutral on purpose: the right amount depends on the person)
    if p["water"] == 0:
        g.append(_item("fluids", "Fluids", "Ask your doctor how much to drink",
                       "You reported about 2 litres a day or less. The right amount depends on your health, the weather, activity and medicines, and "
                       "people with heart or kidney problems are sometimes advised to limit fluids. Ask your doctor what suits you rather than changing "
                       "it on your own."))

    # --- blood pressure
    if p["htn"] == 1:
        g.append(_item("bp", "Blood pressure", "Keep blood pressure under control",
                       "High blood pressure is one of the main causes of kidney damage in diabetes. Take blood-pressure medicines as prescribed and "
                       "check your readings regularly."))
    else:
        g.append(_item("bp", "Blood pressure", "Have your blood pressure checked regularly",
                       "In diabetes, blood pressure is a key kidney-protective number. Ask for it to be measured at each clinic visit."))

    # --- activity, food, weight, sleep, heart
    if p["walk"] == 0:
        g.append(_item("activity", "Activity", "Build regular physical activity",
                       "Regular activity helps blood sugar, blood pressure and weight. Adults are generally advised to aim for about 150 minutes of "
                       "moderate activity a week (for example brisk walking), as far as their doctor allows."))
    if p["diet"] == 0:
        g.append(_item("diet", "Food", "Follow the meal plan from your care team",
                       "A meal plan that keeps blood sugar in range protects the kidneys over time. A dietitian can help build one that fits your food "
                       "habits and budget."))
    if p["bmi"] >= 25:
        g.append(_item("weight", "Weight", "Gradual weight loss helps",
                       "Your BMI is in the overweight range. Gradual weight loss can improve blood sugar and blood pressure. Ask your care team for a "
                       "realistic plan."))
    elif p["bmi"] < 18.5:
        g.append(_item("weight-low", "Weight", "Discuss your nutrition",
                       "Your BMI is low. Talk to your doctor or a dietitian about getting enough nutrition."))
    if p["sleep"] == 0:
        g.append(_item("sleep", "Sleep", "Aim for 7 to 9 hours of sleep",
                       "Regularly sleeping less than 7 hours is linked to poorer blood-sugar and blood-pressure control. Tell your doctor if you have "
                       "trouble sleeping."))
    if p["hd"] == 1:
        g.append(_item("heart", "Heart", "Keep up heart and kidney follow-ups",
                       "Heart and kidney health are closely linked in diabetes. Keep regular follow-up appointments for both."))

    # --- always: blood sugar
    g.append(_item("glucose", "Blood sugar", "Keep blood sugar in your target range",
                   "Staying within the blood-sugar target set by your doctor (including the HbA1c target) is one of the strongest ways to protect "
                   "your kidneys."))

    g.sort(key=lambda x: 0 if x["priority"] == "high" else 1)   # stable: high-priority items first
    return g
