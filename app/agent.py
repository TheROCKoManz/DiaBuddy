"""
Diabetic Assistant Agent — ADK Pipeline
Runs: recipe_agent → carb_agent → insulin_agent via SequentialAgent.
GOOGLE_API_KEY must be set in the environment before this module is imported.
"""
from google.adk.agents.llm_agent import Agent
from google.adk.agents.sequential_agent import SequentialAgent
from google.adk.tools.google_search_tool import google_search


def calculate_insulin_units(carbs_grams: float, pre_meal_sugar_mgdl: float) -> dict:
    """
    Calculates Apidra units needed for carb coverage and blood sugar correction.
    ICR: 1 unit per 15g carbohydrates.
    ISF: 1 unit drops blood sugar by 50 mg/dl.
    Target BG: 100 mg/dl.
    Correction only applied when BG > 150 (high) or < 70 (hypo risk).

    Safety caps:
    - Carb estimate capped at 200g per meal to guard against LLM overestimation.
    - Total dose capped at 15 units. Meals requiring more should be split or
      verified with a physician.
    """
    ICR = 15.0       # grams of carbs per unit
    ISF = 50.0       # mg/dl drop per unit
    TARGET_BG = 120.0
    MAX_CARBS_G = 200.0   # safety ceiling on AI carb estimate
    MAX_DOSE_UNITS = 15.0  # hard cap — doses above this need physician review

    # Warn if the AI carb estimate looks unrealistically high
    carbs_capped = carbs_grams > MAX_CARBS_G
    carbs_grams = min(carbs_grams, MAX_CARBS_G)

    carbs_units = carbs_grams / ICR

    correction_units = 0.0
    if pre_meal_sugar_mgdl > 150:
        correction_units = (pre_meal_sugar_mgdl - TARGET_BG) / ISF
    elif pre_meal_sugar_mgdl < 70:
        correction_units = -1.0

    raw_total = carbs_units + correction_units
    dose_capped = raw_total > MAX_DOSE_UNITS
    total_safe_units = max(0.0, min(raw_total, MAX_DOSE_UNITS))

    # Estimated BG rise from food alone (without insulin), using ISF/ICR ratio.
    # Formula: each gram of carbs raises BG by ISF/ICR mg/dl.
    estimated_bg_rise = round(carbs_grams * (ISF / ICR), 0)
    estimated_peak_bg = round(pre_meal_sugar_mgdl + estimated_bg_rise, 0)

    safety_warnings = [
        "CRITICAL: This is an AI estimation. DO NOT overdose. "
        "Monitor for hypoglycemia, specially if injecting large amounts. "
        "Target level ~100 mg/dl. Please consult with your endocrinologist."
    ]
    if carbs_capped:
        safety_warnings.append(
            "⚠️ SAFETY CAP APPLIED: The AI estimated an unusually high carbohydrate amount. "
            "The dose has been calculated using a maximum of 200g carbs. "
            "Please verify the carb count manually before dosing."
        )
    if dose_capped:
        safety_warnings.append(
            "⚠️ DOSE CAP APPLIED: The calculated dose exceeded 15 units, which is the maximum "
            "this tool will recommend. Large single doses carry serious hypoglycemia risk. "
            "Please split the meal or consult your endocrinologist."
        )

    return {
        "carbs_grams_used": round(carbs_grams, 1),
        "carbs_units_needed": round(carbs_units, 2),
        "corrective_units_needed": round(correction_units, 2),
        "total_apidra_units_recommended": round(total_safe_units, 2),
        "estimated_bg_rise_mgdl": int(estimated_bg_rise),
        "estimated_peak_bg_without_insulin": int(estimated_peak_bg),
        "safety_warning": " | ".join(safety_warnings),
        "hypo_risk": pre_meal_sugar_mgdl < 70,
        "carbs_were_capped": carbs_capped,
        "dose_was_capped": dose_capped,
    }


# Step 1 — searches for each food item, stores structured data in session state
recipe_agent = Agent(
    model="gemini-3-flash-preview",
    name="recipe_agent",
    instruction="""You are an internal data-extraction agent. You are NOT talking to the user.
Read the user's message and identify EVERY individual food or drink item mentioned, along with its quantity.
Items may be separated by commas, periods, "and", or any other delimiter.
For example: "3 slices of medium pepperoni pizza. 1 glass of coke, 30 ml baileys ice cream"
should give you three items: (1) 3 slices of medium pepperoni pizza, (2) 1 glass of coke, (3) 30 ml baileys ice cream.

For EACH item, use google_search to find its nutritional data and compile an ingredient list.

Return your response in this EXACT structured format and nothing else.
Repeat the ITEM block once per food item:

ITEM: <food name>
QUANTITY: <quantity as given>
INGREDIENTS: <ingredient>:<amount per standard serving>, <ingredient>:<amount per standard serving>, ...
SERVING_SCALE: <multiplier to reach the requested quantity, e.g. 2 slices vs 1 standard = 2.0>

Do NOT write prose, titles, instructions, or any other text. Only the ITEM blocks above.""",
    tools=[google_search],
    output_key="recipe_data",
    # Disabling LLM-controlled transfers prevents ADK from injecting Function Calling transfer tools
    # alongside the built-in google_search tool — Gemini disallows mixing both tool types.
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True,
)

# Step 2 — reads recipe_data from session state, calculates total carbs across all items
carb_agent = Agent(
    model="gemini-3-flash-preview",
    name="carb_agent",
    instruction="""You are an internal carbohydrate calculation agent. You are NOT talking to the user.
The recipe data from the previous step is:
{recipe_data}

For EACH ITEM block, calculate the carbohydrates in grams using its INGREDIENTS and SERVING_SCALE.
Then sum all items to get the total.

CRITICAL ACCURACY RULES — under-dosing is recoverable; over-dosing can be fatal:
- Use COOKED weight/volume for rice and lentils, not dry weight. Cooked rice is ~28g carbs per 100g (not 80g).
- Indian sweets (rasgulla, gulab jamun, etc.): one standard rasgulla is ~25-30g carbs, not more.
- Dal (lentil dishes): a typical bowl of dal is ~20-30g carbs. Dal makhani is lower-carb than plain dal.
- Drinks: use actual serving size. 200ml Sprite ≈ 21g carbs.
- Chicken/paneer/meat dishes: protein only, virtually 0 carbs unless the dish has added sugar/sauce.
- When uncertain, use the lower end of the realistic range. Do NOT round up.
- A typical full Indian meal (rice + dal + bread + sabzi) is usually 80-150g carbs total.
  If your total exceeds 200g for a normal home meal, recalculate — you have likely made an error.

Return your response in this EXACT format and nothing else:
ITEM_CARBS: <food name>:<carbs_grams>
ITEM_CARBS: <food name>:<carbs_grams>
... (one line per item)
TOTAL_CARBS_GRAMS: <total number>

Do NOT write prose, explanations, or any other text. Only the lines above.""",
    tools=[],
    output_key="carb_data",
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True,
)

# Step 3 — reads carb_data from session state, calculates and returns the dosage
insulin_agent = Agent(
    model="gemini-3-flash-preview",
    name="insulin_agent",
    instruction="""You are DiaBuddy — a warm, gentle, and deeply caring insulin dosage assistant.
You are speaking directly to a sweet and brave young woman who lives with Type 1 diabetes.
Your tone must always be loving, encouraging, and easy to understand — never clinical or cold.

The carbohydrate data from the previous step is:
{carb_data}

Extract the numeric value from TOTAL_CARBS_GRAMS above.
Also read the patient's pre-meal blood sugar level in mg/dl from the original user message.

You MUST call the calculate_insulin_units tool with:
- carbs_grams: the extracted number from TOTAL_CARBS_GRAMS
- pre_meal_sugar_mgdl: the blood sugar value from the user's message

After calling the tool, write your response in this exact structure:

**Your Apidra Dose: [total_apidra_units_recommended] units** 💉

**Breakdown:**
- 🍽️ Food coverage: [carbs_units_needed] units  *(for [carbs_grams_used]g carbohydrates)*
- 📈 Blood sugar correction: [corrective_units_needed] units  *(to bring your current level toward ~100 mg/dl)*

[If carbs_were_capped is true, insert this block BEFORE the "What will this food do" section:]
> ⚠️ **Carb estimate was unusually high and has been capped at 200g for safety.**
> The dose above is based on 200g carbs. Please count the carbs in your meal manually before injecting.

[If dose_was_capped is true, insert this block prominently:]
> 🚨 **DOSE CAPPED AT 15 UNITS — the raw calculation exceeded this limit.**
> Injecting more than 15 units at once is dangerous. Please split the meal, reduce portions, or speak to your endocrinologist before dosing.

**What will this food do to your sugar?**
Without insulin, this meal is estimated to raise your blood sugar by about **[estimated_bg_rise_mgdl] mg/dl**, which would push you to roughly **[estimated_peak_bg_without_insulin] mg/dl**. Your [carbs_units_needed] units of food coverage are calculated to absorb those carbs and keep you stable.
[If corrective_units_needed > 0, add one warm sentence explaining that the extra units are to also bring down the current high reading. If corrective_units_needed < 0, add a gentle note that she should eat a little something first since her sugar is already low. If corrective_units_needed == 0, skip this sentence.]

**Why this dose?**
[In 1–2 warm, simple sentences summarising the full picture — current sugar level, what the food will do, and how the total dose handles both. Speak as a caring friend, not a doctor.]

⚠️ *[The safety_warning from the tool output, verbatim.]*

[A short, warm, cheerful closing note — encourage her, celebrate that she's taking such good care of herself, remind her to drink water after eating, and let her know she is loved and doing amazingly well. Keep it genuine and sweet, not generic.]""",
    tools=[calculate_insulin_units],
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True,
)

# SequentialAgent guarantees recipe → carb → insulin execution order without LLM orchestration
root_agent = SequentialAgent(
    name="diabetic_assistant_agent",
    sub_agents=[recipe_agent, carb_agent, insulin_agent],
)