# HW4 — submission

**AI assistance:** I used ChatGPT to understand the assignment instructions and plan the workflow.
---

## Part A — Plan on paper (Easy)

> Commit this whole part before any `.py` file exists.

### A1 — The steps

| # | Step | What goes in (types) | What comes out (types) | When it goes wrong | Tool, loop, or model? |
|---|---|---|---|---|---|
| 1 | Identify the required facts | Question (`str`) | District names (`list[str]`), fields (`list[str]`), years (`list[int]), and calculation plan (`str`) | If the question is ambiguous, request clarification or mark it unanswered instead of inventing information. | Model |
| 2 | Validate and dispatch tool requests | Tool name (`str`) and JSON arguments (`str`) | Validated arguments (`dict`) and dispatched request | Return a structured error for invalid JSON, unknown tools, missing parameters, or incorrect types. | Loop |
| 3 | Retrieve authoritative facts | Entity name (`str`) and field name (`str`) | Fact (`dict`) containing value, unit, year, and source document IDs | Return an informative error for unknown or ambiguous entities, unsupported fields, missing facts, or unreadable numbers. Exclude archived profiles and apply corrections. | `lookup` tool |
| 4 | Construct an arithmetic expression | Retrieved facts (`list[dict]`) and calculation plan (`str`) | Arithmetic expression (`str`) including necessary unit conversions | If units are unknown or incompatible, obtain additional information or report that the calculation cannot proceed. | Model |
| 5 | Execute arithmetic safely | Arithmetic expression (`str`) | Numeric result (`float`) or structured error (`dict`) | Reject unsupported syntax, function calls, attribute access, excessive complexity, division by zero, and values outside the allowed range. | `calculate` tool |
| 6 | Compare calculated results | Calculated values (`list[float]`) and comparison requested (`str`) | Selected district or yes/no answer (`str`) and numeric result (`float`) | Handle ties explicitly. If a required calculation fails, correct the request or mark the question unanswered. | Model |
| 7 | Format and record the answer | Selected answer (`str`), numeric result (`float`), and required precision (`int`) | Final answer (`str`) and execution record (`dict`) | Record missing or malformed final answers as unanswered. Stop and record unanswered status when the round limit is reached. | Model formats; loop records |

**How the steps connect:**

Question → identify required facts → validate and dispatch lookup requests → retrieve authoritative facts → construct arithmetic expressions → validate and dispatch calculator requests → calculate → compare results → format and record the final answer.

Each lookup result supplies the facts needed to construct a calculation. Each calculator result supplies the values needed for comparison. The loop validates every tool request and returns its result to the model. These steps repeat when additional facts or calculations are needed, up to the fixed round limit.

**What I am assuming:**

- Population figures refer to the 2025 census unless another year is explicitly requested. Population growth calculations use the 2020 and 2025 census figures.
- Budgets and household water use refer to 2025. School enrolment refers to the 2025/26 school year.
- Archived profiles are superseded and are excluded when retrieving current facts.
- Correction notices override the original profiles. Brightwater's correct area is 921.4 square kilometres.
- Ossbridge and Ossford are different districts. Ambiguous or misspelled names must not be silently assigned to either district.
- Retrieved facts include their units and source document IDs. Corrected facts cite both the original profile and the correction notice.
- One megalitre equals 1,000 cubic metres or 1,000,000 litres. Daily water calculations use 365 days for 2025.
- Budgets stated in million tenge are converted when the requested result uses tenge or thousand tenge.
- Intermediate results are not rounded. Rounding is applied only to the final answer at the required precision.
- Ground-truth answers are used only for evaluation and are never included in model prompts or tool results.
- Missing facts or failed calculations are not replaced with invented values. If they cannot be resolved within the round limit, the question is marked unanswered.

### A2 — The two tools

#### `lookup`

```json 
{
  "type": "function",
  "function": {
    "name": "lookup",
    "description": "Retrieve one factual field about a Nine Rivers district, or a regional water fact using entity Region. Returns the value, unit, relevant year, and source document IDs. Uses current profiles, excludes archived profiles, and applies correction notices. Use calculate for arithmetic.",
    "parameters": {
      "type": "object",
      "properties": {
        "entity": {
          "type": "string",
          "description": "Exact district name, or Region for the regional water tariff and unit conversion."
        },
        "field": {
          "type": "string",
          "enum": [
            "population_2020",
            "population_2025",
            "area_km2",
            "budget_2025_million_tenge",
            "water_use_2025",
            "schools",
            "pupils_2025_26",
            "paved_road_km",
            "founded_year",
            "water_tariff_2025",
            "megalitre_to_cubic_metres"
          ],
          "description": "The requested fact. Water use retains its original unit. The water tariff and conversion fields require entity Region."
        }
      },
      "required": ["entity", "field"],
      "additionalProperties": false
    }
  }
}
```

| Case | What the tool returns |
|---|---|
| success | Returns a value, unit, relevant year, and source IDs. Example: `{"value": 921.4, "unit": "km2", "year": 2025, "sources": ["NR-05", "NR-16"]}`. Timeless facts use `year: null`. |
| Unknown or misspelled entity | Returns an error with possible matching names, without automatically choosing one. |
| Ambiguous entity | Returns an error requesting an exact district name. |
| Unsupported field or entity-field combination | Returns an error identifying the unsupported request and listing valid fields. |
| Archived profile | Excludes the archived profile and uses the current profile. Returns an error if no current fact is available. |
| Corrected fact | Returns the corrected value and cites both the original profile and the correction notice. |
| Missing or unreadable fact | Returns an error identifying the fact that could not be retrieved or parsed. |
| Invalid arguments | Returns an error for missing parameters, incorrect types, unexpected parameters, or excessively long inputs. |
| Unavailable or malformed corpus | Returns a data-loading error instead of crashing. |

**Worst thing it could do with strange or dangerous input:**

The worst plausible outcome is returning the wrong fact, which could produce an incorrect final answer. Very long inputs could also waste processing time. The tool limits input length and output size, validates parameters, and rejects ambiguous names. Inputs are treated as data and cannot execute code, select arbitrary files, or modify the corpus.

#### `calculate`

```json 
{
  "type": "function",
  "function": {
    "name": "calculate",
    "description": "Safely evaluate an arithmetic expression using numeric literals, parentheses, addition, subtraction, multiplication, division, and unary plus or minus. Returns a numeric result without rounding intermediate values. Rejects powers, names, function calls, attribute access, division by zero, and excessive expressions. Expressions are limited to 200 characters and 100 AST nodes; numeric magnitudes must not exceed 1000000000000000.",
    "parameters": {
      "type": "object",
      "properties": {
        "expression": {
          "type": "string",
          "description": "Arithmetic expression to evaluate, for example 44675 / 921.4.",
          "minLength": 1,
          "maxLength": 200
        }
      },
      "required": ["expression"],
      "additionalProperties": false
    }
  }
}
```

| Case | What the tool returns |
|---|---|
| success | Returns `{"result": 7.0}` for the expression `3 + 4`. |
| Invalid arguments | Returns an error for a missing expression, incorrect type, or unexpected parameters. |
| Empty or malformed expression | Returns an error explaining that the expression is empty or has invalid syntax. |
| Unsupported syntax | Returns an error for names, function calls, attribute access, powers, or other disallowed syntax. |
| Division by zero | Returns `{"error": "Division by zero is not allowed."}`. |
| Excessive expression size | Returns an error if the expression exceeds 200 characters or 100 AST nodes. |
| Excessive numeric magnitude | Returns an error if a numeric literal or intermediate result has an absolute value greater than 1000000000000000, or if a result is not finite. |

**Worst thing it could do with strange or dangerous input:**

The worst plausible outcome is an incorrect numerical result due to floating-point precision or a rejected calculation that the model cannot complete. Malicious expressions could attempt code execution or excessive computation. The implementation uses an AST allowlist, never uses eval or exec, rejects powers and all executable constructs, and limits expression size and numeric magnitude.

### A3 — Q-09 by hand

```json 
[
  {
    "role": "user",
    "content": "Which district has the higher population density in 2025, Brightwater or Millbrook, and by how many residents per square kilometre?"
  },
  {
    "role": "assistant",
    "content": null,
    "tool_calls": [
      {
        "id": "call_1",
        "type": "function",
        "function": {
          "name": "lookup",
          "arguments": "{\"entity\":\"Brightwater\",\"field\":\"population_2025\"}"
        }
      },
      {
        "id": "call_2",
        "type": "function",
        "function": {
          "name": "lookup",
          "arguments": "{\"entity\":\"Brightwater\",\"field\":\"area_km2\"}"
        }
      },
      {
        "id": "call_3",
        "type": "function",
        "function": {
          "name": "lookup",
          "arguments": "{\"entity\":\"Millbrook\",\"field\":\"population_2025\"}"
        }
      },
      {
        "id": "call_4",
        "type": "function",
        "function": {
          "name": "lookup",
          "arguments": "{\"entity\":\"Millbrook\",\"field\":\"area_km2\"}"
        }
      }
    ]
  },
  {
    "role": "tool",
    "tool_call_id": "call_1",
    "content": "{\"value\":44675,\"unit\":\"residents\",\"year\":2025,\"sources\":[\"NR-05\"]}"
  },
  {
    "role": "tool",
    "tool_call_id": "call_2",
    "content": "{\"value\":921.4,\"unit\":\"km2\",\"year\":2025,\"sources\":[\"NR-05\",\"NR-16\"]}"
  },
  {
    "role": "tool",
    "tool_call_id": "call_3",
    "content": "{\"value\":37203,\"unit\":\"residents\",\"year\":2025,\"sources\":[\"NR-11\"]}"
  },
  {
    "role": "tool",
    "tool_call_id": "call_4",
    "content": "{\"value\":758.6,\"unit\":\"km2\",\"year\":2025,\"sources\":[\"NR-11\"]}"
  },
  {
    "role": "assistant",
    "content": null,
    "tool_calls": [
      {
        "id": "call_5",
        "type": "function",
        "function": {
          "name": "calculate",
          "arguments": "{\"expression\":\"37203 / 758.6 - 44675 / 921.4\"}"
        }
      }
    ]
  },
  {
    "role": "tool",
    "tool_call_id": "call_5",
    "content": "{\"result\":0.5556561156}"
  },
  {
    "role": "assistant",
    "content": "Millbrook has the higher population density. Using Brightwater's corrected area from NR-16, the difference is approximately 0.6 residents per square kilometre.\nANSWER: Millbrook | 0.6"
  }
]
```

**My arithmetic:**

Population density = population / area.

Brightwater: 44,675 / 921.4 ≈ 48.4859996 residents per square kilometre.

Millbrook: 37,203 / 758.6 ≈ 49.0416557 residents per square kilometre.

Difference: (37,203 / 758.6) − (44,675 / 921.4) ≈ 0.5556561 residents per square kilometre.

The difference is calculated using the unrounded densities and rounded only at the end. To one decimal place, it is 0.6 residents per square kilometre.

Therefore, Millbrook has the higher population density.

Brightwater's area must be taken from correction notice NR-16, which replaces the incorrect 912.4 square kilometres in NR-05 with 921.4 square kilometres.

### A4 — Why I split it this way

I separated factual retrieval from arithmetic because these operations have different responsibilities and failure modes. The lookup tool selects authoritative facts, handles archived profiles and corrections, and provides source IDs. The calculate tool evaluates explicit arithmetic expressions under restricted rules. The model interprets the question and decides which facts and calculations are needed, while the loop validates requests, dispatches tools, and records their results.

An alternative would be one large tool that receives a question and returns the complete answer. I rejected this approach because it would hide retrieval, calculation, and comparison inside one operation, making errors harder to isolate and test. Separate tools make it possible to check whether a wrong answer came from selecting the wrong fact, constructing the wrong expression, or interpreting the result incorrectly.

The design depends most strongly on retrieving authoritative facts with the correct units. A calculator can evaluate an expression correctly even when its inputs are wrong. For example, using Brightwater's uncorrected area would produce an incorrect comparison despite correct arithmetic.

---

## Part B — Build it and run it (Medium)

### What I changed from Part A while coding

<!-- what changed in your plan, and why. "None" is an answer too. -->

### B2 — Tests

```text
...........................                                              [100%]
27 passed in 0.04s

```

### B3 — The loop

- Round limit, and why:
The loop allows a maximum of 10 model calls per question. This provides room for fact retrieval, calculations, and corrections while bounding the number of API calls. If no valid final answer is produced within this limit, the question is marked unanswered.
- Where the logs are:
Pilot logs are saved as timestamped JSON files in outputs/pilot/. Each log contains the conversation, tool definitions, tool requests, arguments, results, execution times, API token usage, and completion status.
- Real Q-09 conversation compared with my A3 version, what is different:
Both conversations retrieved the same four facts, including Brightwater's corrected area of 921.4 km2 from NR-05 and NR-16, and produced the final answer Millbrook | 0.6.
My A3 design used four lookup calls followed by one calculator call containing the complete difference expression, requiring three model rounds including the final answer. The actual run used four lookup calls in round 1, two separate density calculations in round 2, and one difference calculation in round 3, followed by the final answer in round 4.
Therefore, the actual run made seven tool calls instead of five and used four model rounds instead of three. It calculated each density separately before calculating the difference. The difference calculation still used the original expressions rather than rounded intermediate values, returning 0.5556561156405735. The run consumed 3,059 input tokens and 238 output tokens.

### B4 — Three strategies

**What I kept the same:**

All three strategies use gpt-5.6-luna through the Chat Completions API with reasoning_effort="none" and temperature=0.7. The temperature setting was accepted during pilot tests of all three strategies. The twenty questions, original corpus, required answer precision, shared factual instructions, final answer format, and scoring rule are kept fixed. Each question starts a fresh conversation.

S1 receives all documents and answers directly in one model call. S2 receives the same documents, is instructed to solve the question step by step, and generates five independent samples (k=5), followed by voting. S3 receives no documents in its prompt and uses lookup and calculate, with a maximum of ten model calls per question.

The full experiment is performed twice. Questions are processed in file order, with S1, S2, and S3 executed sequentially for each question. No temperature fallback or automatic API retry is used. Logs include every successful call's usage, including all five S2 samples and all S3 rounds. Costs are estimated from token usage using standard rates of $0.20 per million uncached input tokens, $0.02 per million cached input tokens, and $1.20 per million output tokens.

**My rule for a correct answer** 

The evaluator reads the final line in the format ANSWER: <name or yes/no> | <number>. After trimming surrounding whitespace, the answer label must match the ground-truth label exactly, including case. The number must be finite and differ from the ground-truth value rounded to the specified decimals by no more than 10^(-decimals). Decimal arithmetic will be used for comparison.

Missing or malformed answers, API failures, and reaching the S3 round limit without a valid final answer count as unanswered and incorrect. A validly formatted but wrong answer counts as incorrect, not unanswered.

For S2, the five samples vote on the answer label and numeric value rounded to the required precision. Numerically equivalent representations count as the same answer. The most frequent valid answer wins. Ties are resolved by selecting the tied answer that appeared first. Invalid samples receive no vote. If all five samples are invalid, the question is unanswered.

Ground-truth answers and values are used only for evaluation and are never sent to the model. Token totals include all five S2 samples and every S3 round.

| Run | Strategy | Correct /20 | Unanswered | Input tokens | Output tokens | Median seconds per question | Total seconds | Cost ($) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | S1 direct | 6 | 11 | 43620 | 731 | 3.206 | 67.316 | 0.008423 |
| 1 | S2 think and vote (k = 5) | 16 | 1 | 219200 | 13029 | 14.269 | 279.201 | 0.026769 |
| 1 | S3 tools | 19 | 1 | 55239 | 4470 | 9.201 | 186.613 | 0.016223 |
| 2 | S1 direct | 9 | 7 | 43620 | 923 | 3.064 | 61.977 | 0.001991 |
| 2 | S2 think and vote (k = 5) | 17 | 1 | 219200 | 13358 | 14.078 | 291.519 | 0.020468 |
| 2 | S3 tools | 17 | 3 | 55930 | 4406 | 8.221 | 175.361 | 0.015529 |


**Per question (run 1):**

| Question | S1 | S2 | S3 |
|---|:---:|:---:|:---:|
| Q-01 | ✓ | ✓ | ✓ |
| Q-02 | ✓ | ✓ | ✓ |
| Q-03 | ✗ | ✓ | ✓ |
| Q-04 | ✓ | ✓ | ✓ |
| Q-05 | ✗ | ✗ | ✓ |
| Q-06 | ✗ | ✓ | ✓ |
| Q-07 | ✓ | ✓ | ✓ |
| Q-08 | ✓ | ✓ | ✓ |
| Q-09 | ✓ | ✓ | ✓ |
| Q-10 | ✗ | ✓ | ✓ |
| Q-11 | ✗ | ✓ | ✓ |
| Q-12 | ✗ | ✓ | ✓ |
| Q-13 | ✗ | ✗ | ✗ |
| Q-14 | ✗ | ✓ | ✓ |
| Q-15 | ✗ | ✓ | ✓ |
| Q-16 | ✗ | ✓ | ✓ |
| Q-17 | ✗ | ✗ | ✓ |
| Q-18 | ✗ | ✓ | ✓ |
| Q-19 | ✗ | ✓ | ✓ |
| Q-20 | ✗ | ✗ | ✓ |



## Per question: run 2

| Question | S1 | S2 | S3 |
|---|:---:|:---:|:---:|
| Q-01 | ✓ | ✓ | ✓ |
| Q-02 | ✓ | ✓ | ✓ |
| Q-03 | ✓ | ✓ | ✓ |
| Q-04 | ✓ | ✓ | ✓ |
| Q-05 | ✗ | ✓ | ✓ |
| Q-06 | ✗ | ✓ | ✓ |
| Q-07 | ✓ | ✓ | ✗ |
| Q-08 | ✗ | ✓ | ✓ |
| Q-09 | ✓ | ✓ | ✓ |
| Q-10 | ✓ | ✓ | ✓ |
| Q-11 | ✗ | ✓ | ✓ |
| Q-12 | ✗ | ✓ | ✓ |
| Q-13 | ✗ | ✗ | ✗ |
| Q-14 | ✗ | ✓ | ✓ |
| Q-15 | ✓ | ✗ | ✓ |
| Q-16 | ✗ | ✓ | ✓ |
| Q-17 | ✗ | ✓ | ✓ |
| Q-18 | ✗ | ✓ | ✓ |
| Q-19 | ✓ | ✓ | ✓ |
| Q-20 | ✗ | ✗ | ✗ |
---

## Part C — Explain and choose (Hard)

### C1 — Does the tool description matter?

| Question | Calls (your description) | Calls (vague) | Answer (yours) | Answer (vague) |
|---|---:|---:|---|---|
| Q-03 | 7 | 8 | Lindenmoor, 5.3 | Lindenmoor, 5.3 |
| Q-05 | 7 | 7 | Coldharbour, 14235 | Coldharbour, 14235 |
| Q-09 | 7 | 7 | Millbrook, 0.6 | Millbrook, 0.6 |
| Q-13 | 9 | 9 | Unanswered: invalid final format | Unanswered: invalid final format |
| Q-18 | 3 | 3 | yes, 40013 | yes, 40013 |

“Calls” counts individual tool invocations, including both lookup and calculate. I compared S3 run 1 with a new execution of the same five questions after changing only lookup's function description to "Looks things up."

Both descriptions produced four correct answers out of five under the fixed scoring rule. Q-13 was unanswered in both conditions because the final line was "ANSWER: Coldharbour | 4.16%". Although the district and value were correct, the percentage sign violated the required numeric-only format.

The main difference occurred on Q-03. The original description produced seven tool calls across three model rounds. The vague description produced eight tool calls across five model rounds: the conversion-factor lookup moved to a separate round, and the model added an explicit calculator call for the difference. The water-use expressions were mathematically equivalent, and the final answer remained Lindenmoor, 5.3.

For Q-05, Q-09, Q-13, and Q-18, tool-call counts and substantive arguments remained unchanged. Overall, tool calls increased from 33 to 34 and model rounds increased from 17 to 19.

The vague description did not remove all guidance: the tool name, parameter descriptions, allowed field names, shared system instructions, and correction-handling implementation remained available. These could explain why fact retrieval still worked. Because temperature was 0.7 and each condition was observed only once per question, the differences cannot confidently be attributed to the description alone. This experiment shows unchanged accuracy on these five questions, not that tool descriptions never matter.

### C2 — Three mistakes explained

**S1 — Q-05: incorrect numerical answer**

Log: `outputs/run_1/S1/Q-05.json`

The model returned: "ANSWER: Coldharbour | 32921". The expected answer was Coldharbour, 14235, with a tolerance of ±1 tenge. The district was correct, but the numerical difference was incorrect.

The direct response did not show intermediate calculations, so the log does not establish exactly where the error occurred. It could involve division, subtraction, or selecting the figures. S1 generated the number without an external calculator verifying it. A calculator would evaluate the supplied expression reliably within floating-point precision, although the model would still need to select the correct facts and construct the correct expression.


**S2 — Q-05: voting selected a repeated arithmetic error**

Log: `outputs/run_1/S2/Q-05.json`

The five samples returned 14230, 14258, 14233, 14233, and 14226, all with the label Coldharbour. The voting result was "ANSWER: Coldharbour | 14233", with two winning votes out of five. This was the most frequent answer, but not a majority.

Samples 3 and 4 reached 14233 through different inaccurate intermediate divisions. Sample 3 reported "193,283.13" and "207,516.43" tenge per resident, while sample 4 reported "193,282.03" and "207,514.68". Their final answers coincided despite these differences. The expected answer was 14235, so the selected value differed by 2 tenge and failed the ±1 tolerance.

Sampling and voting can reduce occasional errors when the correct answer is consistently more frequent than each incorrect answer. They do not verify arithmetic or guarantee that this condition holds. Here, none of the five answers passed the scoring rule, and voting selected a repeated wrong value. S2 also paid for five complete prompts and responses.


**S3 — Q-13: correct calculation rejected because of final formatting**

Log: `outputs/run_1/S3/Q-13.json`

The model retrieved six population facts and requested three percentage-loss calculations. For Coldharbour, it used `(11902-11407)/11902*100`. Its final line was "ANSWER: Coldharbour | 4.16%".

Coldharbour and 4.16 were correct, but the percentage sign violated the required numeric-only answer format. The parser therefore marked the question unanswered and incorrect. This was an output-format failure rather than an arithmetic failure. The calculator improved numerical reliability but could not ensure that the model followed the final response contract.

The conversation required three model rounds: retrieving facts, requesting calculations, and producing the final response. It made nine tool calls because several requests were grouped within each round. Later requests included the growing conversation history and tool definitions, increasing input-token overhead. The ten-round limit was not reached and did not cause this failure. A future revision could validate and repair final formatting, but the completed experiment retains the original scoring rule and results.

### C3 — Which strategy I would use, and what would change it

I would choose S3 for this problem because it achieved the highest combined accuracy while using fewer tokens, less time, and lower estimated cost than S2.

Across both runs, S3 answered 36 out of 40 correctly (90%), compared with 33 out of 40 for S2 (82.5%) and 15 out of 40 for S1 (37.5%). S3 used 111,169 input tokens and 8,876 output tokens, compared with S2's 438,400 input tokens and 26,387 output tokens. Its total question execution time was 361.974 seconds, compared with 570.720 seconds for S2. Estimated cost was $0.031752 for S3 and $0.047237 for S2.

I would not choose S2 here because five samples repeatedly send the full corpus and generate multiple responses without guaranteeing correct arithmetic. On Q-05 in run 1, voting selected 14233 rather than the expected 14235. S3 delegates arithmetic to a restricted calculator and retrieves facts with source IDs.

S1 was fastest and cheapest, taking 129.293 seconds and costing an estimated $0.010414 across both runs. However, its substantially lower accuracy and 18 unanswered results make it unsuitable when reliable answers are important. The unanswered count includes responses rejected for formatting, so the accuracy comparison measures the complete answering system rather than mathematical ability alone.

My choice would change under the following conditions:

- With a strict latency limit or a very small budget, I would choose S1 if lower reliability were acceptable. Its median response time was approximately three seconds per question in both runs.
- For simple factual questions with no arithmetic and a small corpus, I would initially choose S1 and validate it on representative examples. The calculator's main benefit would no longer apply.
- With 1,000 times more documents, I would retain the S3 approach but replace the current lookup implementation with indexed retrieval. This would avoid sending the entire corpus with every question.
- If tools were unavailable but multiple samples were affordable, I would choose S2 over S1 based on its higher observed accuracy, while recognising that voting does not verify arithmetic.

S3 did not win outright in every run: S2 and S3 both scored 17/20 in run 2. Therefore, I regard S3 as the best-supported choice for this dataset and implementation, rather than a universally superior strategy.

### C4 — How sure I can be

The two runs showed noticeable variation. S1 improved from 6/20 to 9/20, a change of three questions or 15 percentage points. S2 improved from 16/20 to 17/20, a change of five percentage points. S3 decreased from 19/20 to 17/20, a change of ten percentage points.

The difference between the two strongest strategies was not stable. S3 exceeded S2 by three questions in run 1, but they tied in run 2. Their combined accuracy difference was 7.5 percentage points, which is smaller than S3's ten-percentage-point change between runs. These results support a tentative preference for S3, but do not establish a reliable accuracy advantage over S2.

The 40 evaluations per strategy are repeated measurements of the same twenty questions, not forty independent questions. The dataset is small and covers one fictional region. Accuracy also depends on the scoring rule: some numerically correct responses were marked unanswered because their final format was invalid.

Before trusting the ranking, I would start with at least 200 distinct questions covering arithmetic, unit conversion, corrections, archived profiles, and similar district names, and run each strategy at least five times. This is a proposed starting point rather than a guaranteed sufficient sample size. I would compare strategies on the same questions, estimate uncertainty while accounting for repeated questions, and increase the sample if the accuracy difference remained uncertain.

Cost also varied despite fixed settings. For example, S1 used 43,620 input tokens in each run, but its estimated cost decreased from $0.008423 to $0.001991. Because the calculation applies different rates to cached and uncached input, cached-token usage should be examined before attributing this difference to strategy efficiency. Future conclusions should distinguish total token demand, caching effects, execution time, and answer reliability.

### Final questions

1.When the model sends a tool_calls message, it has generated requests describing which functions to call and their arguments. The Python functions have not run yet. My loop parses and validates those requests, executes the permitted functions, and returns a result for each tool_call_id.

2.The arguments field arrives as a string containing JSON, which represents the requested parameters in a transportable format. My loop uses json.loads to convert it into a dictionary, then validates the names, required fields, types, and permitted values. Passing the string directly would not provide the named parameters expected by the function, and parsing alone would not establish that the request is valid.

3.I measured the tool-definition overhead using two API requests with identical messages, one without tools and one with both definitions and tool_choice="none". Input usage increased from 10 to 425 tokens, giving an additional 415 input tokens for this configuration. The measurement is saved in outputs/tool_token_measurement.json; this overhead is included again whenever the definitions are sent in an S3 request.

4.In run 1, S2 cost $0.026769 compared with S1's $0.008423, an additional $0.018346, or approximately 3.18 times as much. In run 2, S2 cost $0.020468 compared with $0.001991, an additional $0.018477, or approximately 10.28 times as much. S2 sent five complete prompts per question and generated five responses, while S1 made one call. The cost ratios differ from five because output lengths and cached-input usage affect the estimated charges.

5.The maximum was five model rounds, reached by Q-14 in both runs and Q-17 in run 2. In the inspected Q-14 run 1 log, the model retrieved four district facts in round 1, requested the conversion factor in round 2, calculated two daily water-use values in round 3, calculated their difference in round 4, and answered in round 5. Q-17 in run 2 followed the same pattern but also retrieved the water tariff, giving nine tool calls compared with Q-14's eight. These executions used extra rounds because the model separated the conversion lookup and difference calculation instead of grouping them into earlier requests.

6.For 100,000 documents, I would replace repeatedly reading and scanning the corpus with an indexed retrieval system. Exact entity and field queries could use a database index, while less structured queries could use keyword or semantic search. The retrieval process would still enforce year, archive, and correction rules and return limited results with source IDs. I would test retrieval accuracy separately because a calculator cannot repair facts retrieved from the wrong documents.

7.My calculator parses expressions with ast and evaluates only numeric literals, approved arithmetic operators, and unary signs; it never uses eval or exec. It rejects names, calls, attribute access, powers, division by zero, expressions over 200 characters or 100 AST nodes, and excessive numeric magnitudes. The required malicious-input tests passed, including __import__('os').system('echo hi'), (1).__class__, and 9**9**9. The model can still provide an incorrect expression, trigger rejection, or encounter floating-point rounding, so safe execution does not guarantee a correct answer.

8.Tools helped most with multi-step numerical questions involving division, unit conversion, and differences, such as Q-05, where S1 and S2 failed in run 1 but S3 returned the correct budget difference. They also made source selection explicit, including Brightwater's corrected area in Q-09. They did not improve the scored outcome for Q-13: all three strategies failed in both runs, and the inspected S3 log showed correct reasoning rejected because the final number included a percentage sign. For questions such as Q-01, which all strategies answered correctly in both runs, tools provided no observed accuracy gain.
