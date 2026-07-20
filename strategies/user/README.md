# Your strategies live here

Drop any strategy you write — or that an AI agent writes for you — into this
directory. **Everything here is gitignored**, so your generated alpha never
lands in a commit, a fork, or a pull request.

```
strategies/user/my_idea.py     # ignored, private to you
strategies/examples/           # tracked, ships with the repo
```

Run one:

```bash
hlbt run --strategy strategies/user/my_idea.py --symbol BTC --timeframe 15m
```

Start from `strategies/examples/` for the shape of a strategy class, or see
[`docs/WRITING-STRATEGIES.md`](../../docs/WRITING-STRATEGIES.md).

If you *want* to share one, force-add it:

```bash
git add -f strategies/user/my_idea.py
```
