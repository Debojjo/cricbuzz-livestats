# Deployment

## The one thing to know first

The database file and the raw API cache are **not** in Git (`.gitignore`). A hosted app
starts from a fresh copy of the repository, so it needs the data from somewhere:

1. **Best:** commit a snapshot of your database. `python -m data.make_snapshot` writes
   `data/snapshot/cricbuzz_snapshot.db` (a compact copy of everything you loaded).
2. With the setting `AUTO_SETUP=1` the app copies that snapshot to `data/cricbuzz.db` on
   its first start.
3. **Fallback:** with no snapshot, `AUTO_SETUP=1` builds a small demo from the saved sample
   files plus the fictional history. The app always starts.

Hosted file systems are temporary: edits made through the CRUD page are lost when the app
restarts. That is fine for a demo and is stated on the Settings page.

## Option 1 - Streamlit Community Cloud (recommended, free)

**A. Put the project on GitHub (first time)**

1. Create the snapshot and commit it:
   ```
   python -m data.make_snapshot
   git add data/snapshot
   git commit -m "data: add database snapshot"
   ```
2. On github.com click **New repository**, give it a name (for example
   `cricbuzz-livestats`), choose **Public**, and do **not** tick "Add a README" (the
   repository must be empty). Copy its address, which ends in `.git`.
3. Check that your key is not tracked: `git ls-files .env` must print nothing.
4. Connect and push (a browser window may ask you to sign in to GitHub):
   ```
   git remote add origin https://github.com/<you>/cricbuzz-livestats.git
   git push -u origin master
   ```

**B. Deploy**

1. Go to <https://share.streamlit.io>, sign in with GitHub and click **Create app**
   (then *Deploy a public app from GitHub*). Allow access to the repository if asked.
2. Repository: yours. Branch: `master`. **Main file path: `main.py`**.
3. Open **Advanced settings**. Python version: **3.12**. In **Secrets** paste:
   ```
   AUTO_SETUP = "1"
   API_CALLS_OFFSET = "14"
   ```
4. Click **Deploy**. The first start copies the snapshot into place (a few seconds);
   later starts are instant. The address looks like `https://<name>.streamlit.app`.

**Do not put `RAPIDAPI_KEY` in the secrets of a public app.** Anyone could press the live
buttons and spend your 200 monthly requests. Without a key the Live Matches page shows a
friendly message and the *Recent results* tab still works from saved data. Record your
demo video locally, where the key is in `.env`.

## Option 2 - Docker (any host)

A `Dockerfile` is included (I could not build it in my environment, so test it once):

```
docker build -t cricbuzz-livestats .
docker run -p 8501:8501 -e AUTO_SETUP=1 cricbuzz-livestats
```

Open <http://localhost:8501>. Mount a volume on `/app/data` to keep CRUD changes.

## Option 3 - Render or Railway

Both read the included `Procfile` (`web: streamlit run main.py --server.port $PORT ...`).
Create a *web service* from the GitHub repository, set build command
`pip install -r requirements.txt`, and add the environment variable `AUTO_SETUP=1`.
Free tiers sleep when idle and wake slowly.

## Option 4 - Azure App Service or AWS

Both can run the same Docker image (Azure Web App for Containers; AWS App Runner or
Elastic Beanstalk). Use them if the project must live in a company cloud account. For
more than one user editing data, move from SQLite to a managed PostgreSQL first
(SQLite allows only one writer at a time); the change is confined to
`database/schema.sql` and `utils/db_connection.py`.

## Checklist before sharing the link

- [ ] Home page shows the real and sample counts
- [ ] SQL Analytics: the sample-data switch changes Q5
- [ ] Custom SQL box refuses `DROP TABLE players`
- [ ] Live Matches → Recent results shows a scorecard
- [ ] No secrets in the repository (`git log -p | findstr RAPIDAPI_KEY` prints nothing)
