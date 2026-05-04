# Privacy Notes

## What StreamFader Collects

StreamFader does not require an account and does not collect personal information.

Anonymous engagement events (fader position, genre selections, card interactions) may be logged locally for product improvement. These logs contain no personally identifiable information and are not shared with third parties.

## Email Capture (Optional)

If `BREVO_API_KEY` is configured, StreamFader may offer a newsletter signup. Email addresses submitted through this form are stored in Brevo and governed by Brevo's privacy policy. Addresses are never sold or shared.

## What StreamFader Is Not

StreamFader is a **discovery tool**. It does not stream, host, or distribute any film or TV content. All posters, metadata, and ratings data come from third-party APIs (TMDb, MDBList, Trakt, TVmaze) under their respective terms of service.

## What Should Never Be Committed to This Repo

- API keys or tokens
- Subscriber email lists
- Raw IP logs or analytics exports
- User preference files (`data/preferences*.json`)
- Watchlist files (`data/watchlist*.json`)
- Any cache files containing user-generated data

The `.gitignore` is configured to exclude all of the above. Do not override it.

## Contact

Questions about privacy: support@creativekonsoles.com
