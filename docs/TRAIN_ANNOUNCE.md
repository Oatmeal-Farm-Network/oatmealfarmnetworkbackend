# Train announce — development → staging → prod

Effective now:

`feature/* → GCP/*-development → GCP/*-staging → main`

- **development** = where development happens (`GCP/*-development`, `*-development` Cloud Run)
- **staging** = QA / UAT / pre-prod (`GCP/*-staging`)
- **main** = production

`GCP/*-testing` is retiring. Open new work against **development**, then promote development → staging → main.

Questions: @dbanoth / @OatmealAIJohn
