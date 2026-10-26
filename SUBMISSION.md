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
| 1 | S1 direct | | | | | | | |
| 1 | S2 think and vote (k = 5) | | | | | | | |
| 1 | S3 tools | | | | | | | |
| 2 | S1 direct | | | | | | | |
| 2 | S2 think and vote (k = ) | | | | | | | |
| 2 | S3 tools | | | | | | | |

**Per question (run 1):**

| Question | S1 | S2 | S3 |
|---|:---:|:---:|:---:|
| Q-01 | | | |
| Q-02 | | | |
| Q-03 | | | |
| Q-04 | | | |
| Q-05 | | | |
| Q-06 | | | |
| Q-07 | | | |
| Q-08 | | | |
| Q-09 | | | |
| Q-10 | | | |
| Q-11 | | | |
| Q-12 | | | |
| Q-13 | | | |
| Q-14 | | | |
| Q-15 | | | |
| Q-16 | | | |
| Q-17 | | | |
| Q-18 | | | |
| Q-19 | | | |
| Q-20 | | | |

---

## Part C — Explain and choose (Hard)

### C1 — Does the tool description matter?

| Question | Calls (your description) | Calls (vague) | Answer (yours) | Answer (vague) |
|---|---:|---:|---|---|
| | | | | |

### C2 — Three mistakes explained

### C3 — Which strategy I would use, and what would change it

### C4 — How sure I can be

### Final questions

1.
2.
3.
4.
5.
6.
7.
8.
