## What's New in Version 1.0.0

The first stable release. Scores has covered eleven sports for a while now; this
is the version that says so out loud, and it brings a new way to follow a game.

### Hear where a play happened

Basketball and hockey plays now play a tone for where they were, the way pitches
already did in baseball. The note says how far from the basket or the goal the
play was — close in is a high note — and the stereo position says where it was
across the court or the ice.

- **Alt+P** plays the selected play.
- **Alt+S** plays every located play in the period, in order.
- **Shift+F10** offers the same as a menu, and there's a Play Audio button too.

Each play reads its location as part of its entry in the list — "from three,
left side", "near end, in the slot" — so you hear where it happened just by
moving through the plays, and nothing is spoken over the tone itself. Each
period heading says how many of its plays can be heard.

Hockey sides are as heard facing the goal at that end, so a shot from the left
circle sounds like the left at either end of the ice.

Not every play has a location. Substitutions, timeouts, free throws and most
face-offs arrive without one, so about a third of basketball plays and one in
twenty hockey plays stay silent and say so rather than guess.

Covers the NBA, WNBA, men's and women's college basketball, the NHL and men's
and women's college hockey. Football and soccer plays carry no coordinates from
ESPN, so they have no audio.

### Fixes

- **The MLB Pitch Audio button never appeared.** It was shown only when the
  sport was "baseball", but the check it was given reports league names like
  "MLB", so the button was hidden on every game. Alt+P on a pitch always
  worked; the button now sits beside it.

### Upgrading

Scores will offer the update itself, or run `Scores-1.0.0-Setup.exe`.

The project has moved to the TheIdeaPlace/Scores repository, and the updater,
the installer and the documentation all point there now. Nothing changes for an
existing install — the update arrives as usual.

---
