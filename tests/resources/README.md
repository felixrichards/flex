# Test Resources

Drop scoreboard parser fixtures in this folder.

## Files

- `scoreboard_cases.json`:
  - list of test cases for parser regression tests
- image files:
  - place under this directory (for example `scoreboards/case_01.png`)

## `scoreboard_cases.json` shape

```json
[
  {
    "id": "case_01",
    "image": "scoreboards/case_01.png",
    "expected": {
      "win": [
        {"player": "player", "champion": "champion", "kda": "0/0/0"},
        {"player": "player", "champion": "champion", "kda": "0/0/0"},
        {"player": "player", "champion": "champion", "kda": "0/0/0"},
        {"player": "player", "champion": "champion", "kda": "0/0/0"},
        {"player": "player", "champion": "champion", "kda": "0/0/0"}
      ],
      "lose": [
        {"player": "player", "champion": "champion", "kda": "0/0/0"},
        {"player": "player", "champion": "champion", "kda": "0/0/0"},
        {"player": "player", "champion": "champion", "kda": "0/0/0"},
        {"player": "player", "champion": "champion", "kda": "0/0/0"},
        {"player": "player", "champion": "champion", "kda": "0/0/0"}
      ],
      "date": null
    }
  }
]
```
