# Christofides on a ½-headway model

Model (`headways/simple_model.py`). There's no timetable: the cost of a route is ride time, plus transfer time, plus ½ the average headway of each line you board. The headway is the hourly average for that line, direction and station, at the hour the plan expects you there. Each run iterates five times, re-estimating those hours from the previous tour, for start times of 4–8 am. Christofides plans over station-to-station costs, and the expected time is then added up along the tour, tracking which train you're on. All runs use express rules (passing through counts), as Trail of Bits did, unless marked local.

| Variant | Expected time (model) | Same tour replayed on the real timetable |
|---|---|---|
| Undirected (Trail of Bits style), **hourly scheduled** headways | **20 h 11 min** | 25 h 58 min |
| Undirected, hourly **observed** headways (last week) | 20 h 19 min | 25 h 58 min |
| Undirected, **all-day average** headways (Trail of Bits' exact assumption) | 21 h 10 min | 26 h 16 min |
| Directed, hourly scheduled headways | 23 h 51 min | 25 h 40 min |
| Directed, hourly observed headways | 24 h 25 min | 25 h 23 min |
| Local rules, directed, hourly scheduled | 25 h 16 min | 25 h 59 min |
| *Reference: Trail of Bits (undirected, all-day averages)* | *20 h 42 min* | *not replayed* |
| *Reference: our LKH + timetable annealing, express* | *n/a* | *23 h 47 min* |

Takeaways:
- **On its own terms, hourly headways beat Trail of Bits.** In the same kind of expected-time model, using the headway for the actual hour gets 20 h 11 min, 31 min under their 20 h 42 min. With their exact all-day averages, our Christofides tour comes out at 21 h 10 min, so the gain comes from time-of-day headways rather than the algorithm. Differences in transfer times and graph details also play a part.
- **The undirected expected time is optimistic by almost 6 hours.** Ignoring direction lets a tour turn around anywhere at no cost. Replayed on the real weekday timetable, those tours take about 26 hours.
- **The directed model is much more honest.** Its expected 23 h 51 min becomes 25 h 40 min on the timetable.
- **Timetable annealing still wins on real time.** The LKH plan, annealed against the actual trains, reaches 23 h 47 min of real, scheduled travel. That's faster than any Christofides tour once replayed.
