# Experiment results

Cost is estimated from API usage and standard token rates.
Total seconds is the sum of question execution times.

| Run | Strategy | Correct /20 | Unanswered | Input tokens | Output tokens | Median seconds per question | Total seconds | Cost ($) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 2 | S1 direct | 9 | 7 | 43620 | 923 | 3.064 | 61.977 | 0.001991 |
| 2 | S2 think and vote (k = 5) | 17 | 1 | 219200 | 13358 | 14.078 | 291.519 | 0.020468 |
| 2 | S3 tools | 17 | 3 | 55930 | 4406 | 8.221 | 175.361 | 0.015529 |

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

Completed evaluations: 60/60.
API errors recorded: 0.
Estimated run cost: $0.037987.
