# Candy Call

A small web app for the harvest party: booth volunteers tap one button to ask for a candy refill, and the candy team sees every booth on a live red/green grid.

It works in any modern phone or tablet browser (iPhone, iPad, Android) with nothing to download.

| Page | Who uses it | Address |
|---|---|---|
| Booth | Volunteers at each booth, on their phones | `/booth` |
| Team dashboard | The candy team, best on an iPad | `/team` |
| Home | Lets anyone pick booth or team | `/` |

## How it works on the night

1. **A booth volunteer** opens the booth link and types their booth number (letters and/or digits, like `A7` or `12`). The phone remembers it.
2. They tap **Need more candy**. That booth's light turns **red** on the team dashboard, which also shows how long it has been waiting.
3. **The candy team** taps the red booth, then **Mark in progress & notify booth**. The light turns **amber**, and the booth's phone shows **"Candy is on its way!"**
4. The booth's message clears by itself after 45 seconds and the button comes back, so they can ask again whenever they need to.
5. When the runner drops off the candy, tap the amber booth and choose **Refill delivered**. It goes back to **green**, and the booth's refill count goes up by one.

Team dashboard extras:
- **Sound on** plays a chime for each new request. Phones and tablets only allow sound after a tap, so turn it on once at the start of the night.
- **Needs first** moves waiting booths to the top, with the longest wait first.
- **Setup** lets you load your booth list (`A1-A12, B1-B8, 21`), sort the grid, and **Start a new night**, which turns every booth green and zeroes the counts.
- Booths not on your list are added automatically the first time a volunteer signs in with that number.

**Event overview** (`/admin`, the third choice on the home page): candy left, refills made (from the app and in person), average time to answer a request, the busiest booth, refills over time, and a table of refills for each booth. Enter what you started with and how much one refill uses under **Candy on hand**, and add candy there if you buy more during the night. Changing those numbers needs the team PIN. **Download spreadsheet** saves everything, including a time-stamped log of every refill. **Start a new night** on the team dashboard clears the refill log but keeps your candy numbers.

**Put it on the home screen like an app (optional):**
- iPhone or iPad: open the page in Safari → Share → **Add to Home Screen**.
- Android: open the page in Chrome → menu (⋮) → **Add to Home screen** or **Install app**.

The booth page installs as **Candy Call** and the team page as **Candy Team**. Both open full screen with no address bar. On iPhone and iPad the home-screen icon keeps its own memory, so the first time it opens it asks for the booth number (or team PIN) once more.

**QR code tip:** a link ending in `#A7`, like `https://your-site/booth#A7`, opens straight to booth A7. Print a QR code for each booth's sign and volunteers never have to type anything.

## Running it

It needs Python 3.8 or newer and nothing else: no packages, no database.

### Option A: a laptop at the church (free, 2 minutes)

Run this on a laptop that stays on the church Wi-Fi all evening:

```bash
python3 server.py
```

Then find the laptop's local address (on a Mac: System Settings → Wi-Fi → Details, for example `192.168.1.42`). Volunteers on the **same Wi-Fi** go to `http://192.168.1.42:8000/booth`, and the team iPad goes to `http://192.168.1.42:8000/team`.

Caveats: phones must be on that Wi-Fi rather than cellular data, and some guest networks block devices from reaching each other. Test with one phone beforehand.

### Option B: a free cloud host (works on cellular, about 15 minutes to set up)

This repo includes a `render.yaml` for [Render](https://render.com):

1. Put this folder in a GitHub repository.
2. In Render, choose **New → Blueprint** and pick the repo. It reads `render.yaml` and deploys.
3. You get an address like `https://candy-call.onrender.com`. Share `/booth` with volunteers and open `/team` on the iPad.

Render's free plan goes to sleep after about 15 minutes without visitors, and the first visit after that takes about a minute to wake it up. Open the team dashboard 5 minutes before the party starts, and keep it open. For peace of mind on the night you can switch to Render's paid Starter plan for that month (about $7) and switch back afterward.

### Settings

Set these as environment variables (in Render, under **Environment**):

| Variable | What it does | Default |
|---|---|---|
| `TEAM_PIN` | If set, the team dashboard asks for this PIN before anyone can mark booths. Recommended on a public host. | none |
| `ACK_SECONDS` | How long the booth shows "Candy is on its way!" | `45` |
| `PORT` | Port to listen on (Render sets this for you) | `8000` |

The booth list and current statuses are saved to `data.json`, so restarting the laptop server keeps everything. On Render's free plan that file resets when the service restarts, so re-add the booth list if that happens.
