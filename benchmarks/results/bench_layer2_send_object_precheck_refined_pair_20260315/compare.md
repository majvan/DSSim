| Scenario | Before (ev/s) | After refined (ev/s) | Delta |
|---|---:|---:|---:|
| Lite try_send -> ISubscriber | 2,566,146 | 1,627,406 | -36.58% |
| Lite try_send -> generator | 2,632,569 | 1,638,201 | -37.77% |
| PRE observers | 87,582 | 82,321 | -6.01% |
| POST_HIT observers | 88,682 | 86,574 | -2.38% |
| POST_MISS observers | 90,612 | 87,160 | -3.81% |
| Hit at idx=0 | 310,917 | 317,974 | +2.27% |
| Hit at idx=S//2 | 84,459 | 83,464 | -1.18% |
| Hit at idx=S-1 | 53,398 | 49,626 | -7.06% |
| Miss (no consumer hit) | 54,372 | 51,577 | -5.14% |
| Hit-ratio 10% | 55,900 | 54,170 | -3.09% |
| Hit-ratio 50% | 92,639 | 85,103 | -8.13% |
| Hit-ratio 90% | 224,426 | 195,180 | -13.03% |
| Miss: None + exact value | 24,709 | 19,336 | -21.75% |
| Miss: None + callable | 23,275 | 18,958 | -18.55% |
| Miss: None + get_cond() filter | 22,025 | 17,608 | -20.05% |
| Miss: None only | 26,546 | 20,717 | -21.96% |
| Miss: direct_call | 46,687 | 46,876 | +0.40% |
| Hit: None + exact value | 281,368 | 224,498 | -20.21% |
| Hit: None + callable | 269,135 | 223,754 | -16.86% |
| Hit: None + get_cond() filter | 258,561 | 213,343 | -17.49% |
| Hit: None only | 284,890 | 238,530 | -16.27% |
| Hit: direct_call | 357,977 | 282,242 | -21.16% |
| NotifierDict pass-through | 1,613,788 | 1,117,439 | -30.76% |
| NotifierRoundRobin pass-through | 48,046 | 43,561 | -9.33% |
| NotifierPriority pass-through | 37,962 | 36,662 | -3.42% |
| NotifierDict churn (cleanup path) | 53,142 | 53,674 | +1.00% |
| NotifierRoundRobin churn (cleanup path) | 36,105 | 35,571 | -1.48% |
| NotifierPriority churn (cleanup path) | 50,751 | 49,516 | -2.43% |
| NotifierDict in-callback mutation | 53,001 | 50,906 | -3.95% |
| NotifierRoundRobin in-callback mutation | 39,784 | 38,477 | -3.29% |
| NotifierPriority in-callback mutation | 32,640 | 31,412 | -3.76% |
| signal->run path (S consumers) | 57,304 | 57,029 | -0.48% |
| S=1 | 484,838 | 422,961 | -12.76% |
| S=4 | 263,577 | 239,626 | -9.09% |
| S=16 | 98,858 | 88,405 | -10.57% |
| S=64 | 27,661 | 26,995 | -2.41% |
| S=256 | 6,719 | 6,748 | +0.43% |
