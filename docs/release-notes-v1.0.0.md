## What's New in Version 1.0.0

The first stable release. Scores has covered eleven sports for a while now; this
is the version that says so out loud, and it brings a new way to follow a game:
basketball and hockey plays now play a tone for where they happened, the way
pitches already did in baseball.

The note says how far from the basket or the goal the play was — close in is a
high note — and the stereo position says where it was across the court or the
ice. It covers the NBA, WNBA, men's and women's college basketball, the NHL and
men's and women's college hockey. Football and soccer plays carry no coordinates
from ESPN, so they have no audio.

### Windows: hear where a play happened

- **Alt+P** plays the selected play, **Alt+S** plays every located play in the
  period in order, **Shift+F10** offers the same as a menu, and there's a Play
  Audio button beside the plays.
- Each play reads its location as part of its entry in the list — "from three,
  left side", "near end, in the slot" — so you hear where it happened just by
  moving through the plays. Nothing is spoken over the tone itself.
- Each period heading says how many of its plays can be heard.

### Windows: other fixes

- **The MLB Pitch Audio button never appeared.** It was shown only when the
  sport was "baseball", but the check it was given reports league names like
  "MLB", so the button was hidden on every game. Alt+P on a pitch always
  worked; the button now sits beside it.

### iPhone: hear where a play happened

Open a basketball or hockey game, choose Plays, and expand a period. Each play
now says where it happened as part of what VoiceOver reads.

To hear the tone:

- **VoiceOver:** the "Play location" action on a play, or "Play locations" on a
  period heading to walk the whole period in order.
- **Without VoiceOver:** tap a play.

Headphones help. Hockey sides are as heard facing the goal at that end, so a
shot from the left circle sounds to the left at either end of the ice.

The "Play location" action appears only on plays that have a location. About a
third of basketball plays have none — free throws, substitutions, timeouts — and
those say "This play has no location" rather than play a tone that would be a
guess. Each period heading says how many of its plays can be heard, and nothing
is spoken over the tone itself.

Baseball pitch audio is unchanged.

### Upgrading

On Windows, Scores will offer the update itself, or run
`Scores-1.0.0-Setup.exe`. On iPhone, update through TestFlight.

The project has moved to the TheIdeaPlace/Scores repository, and the updater,
the installer and the documentation all point there now. Nothing changes for an
existing install — the update arrives as usual.

---

**Platforms:** Windows 10 or later; iPhone through TestFlight
