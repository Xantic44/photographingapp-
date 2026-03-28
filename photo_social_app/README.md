# Photo Social App (Current Learning Build)

Current local path:
`C:\Users\Diar_\Desktop\pythonprojects\photo_social_app`

## Long-Term Project Vision

A photography-focused social app starter with:
- login/register
- profile page
- what's new page showing many other user uploads in just pictures and user can press on the pic(short video in future) and get to the post.
- personalized feed from followed users
- follow recommendations small section and under is message inbox settings, what's hot(newest uploads or trending by likes and views and comments) (right side)
- comments (create, edit, delete by owner) also has timestamp and users can reply to the comment in a comment section
- non perzonalized feed from followed users which shows what's latest, whats trending and other user uploads like the nr -3 in this file states
- like tiktok scroll function and comment section, like, comment, share: copy link for now..later we will have to share to IG tiktok and facebook..visually warm and pleasing, a warmth feeling and soft pleasurable visual design for the user

## Current Step

This project is currently a working Flask + SQLite notes app with:
- warm Tailwind UI (amber/orange/rose theme)
- add note flow (`POST /api/notes`)
- latest note message (`GET /api/hello`)
- latest notes list (`GET /api/notes`)
- global launcher command (`run-photoapp`)

## Run

Use the global launcher:

```powershell
run-photoapp
```

Then open:
`http://127.0.0.1:5000`

If you need manual run:

```powershell
cd C:\Users\Diar_\Desktop\pythonprojects\photo_social_app
.\.venv\Scripts\python.exe app.py
```

## API Endpoints

- `GET /api/hello`
  Returns latest note text as `{ "message": "..." }`

- `GET /api/notes`
  Returns latest 10 notes as:
  `{ "notes": [ { "id": 1, "text": "..." } ] }`

- `POST /api/notes`
  Accepts JSON body:
  `{ "text": "your note" }`

## Project Files

- `app.py` -> Flask routes + SQLite logic
- `templates/index.html` -> Tailwind layout
- `static/script.js` -> fetch/save/render note logic
- `static/styles.css` -> reserved for optional custom CSS
- `photo_social.db` -> SQLite database file
- `run-photoapp.cmd` -> global launcher command

## Next Logical Steps

1. Add delete note endpoint + button.
2. Add edit note endpoint + inline update UI.
3. Add timestamps (`created_at`) and render them in list.
