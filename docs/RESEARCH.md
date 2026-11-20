# Research notes: how reshop works in real stores

These notes guided the simulator's defaults. They come from public posts by store team members on
The Break Room (a forum for Target workers) and r/Target. They are **anecdotes from individual
stores**, not official policy or measured data. In the app, inputs based on them are labeled
`forum`; everything else is labeled `assumption`.

## What workers describe

| Topic | What posts describe | How the simulator uses it |
|---|---|---|
| Where reshop waits | Carts or bins behind Guest Services, often split by area (for example softlines, hardlines, market, seasonal, plus small bins for electronics and beauty). | Reshop arrives at Guest Services already sorted by department. |
| Cart limits | One store described a rule of no more than 10 reshop items in a cart. | `cart_capacity` defaults to 10 (`forum`). |
| How often it gets collected | Collection every 30 minutes to every hour, or "when the cart is full" with a walkie call. | Dedicated trips trigger at 30 min of age; hybrid trips at 60 min (`forum`). |
| Collecting during trips already made | Team members grab reshop for their area when coming back from break or lunch, or after backup cashiering. | Break and backup-cashier tasks can pick up reshop on the walk back (the "during existing trips" strategy). |
| Wasted walking | Posts describe people walking up front repeatedly for one to three items. | This is the inefficiency the project tests. |
| Backlog | Many posts describe several full carts left at close when staffing is short. | The dashboard reports reshop left at close next to efficiency, so a method can't "win" by doing less. |

## Sources

- [Poll: Your store's reshop process](https://www.thebreakroom.org/threads/poll-your-stores-reshop-process.19502/) — cart setups, collection timing (every 30 min / every hour), calling teams when carts fill.
- [How to ensure all reshop is put away by close of business](https://www.thebreakroom.org/threads/how-to-ensure-all-reshop-is-put-away-by-close-of-business.25341/) — picking up reshop when returning from break or lunch; collecting at set times.
- [Reshop at Guest Service?](https://www.thebreakroom.org/threads/reshop-at-guest-service.18759/) — grabbing reshop when coming to the floor or after backup cashier; backlogs of several carts.
- [New reshop policy](https://www.thebreakroom.org/threads/new-reshop-policy.12898/) — a reported 10-items-per-cart rule.
- [Guest Service reshop hell](https://www.thebreakroom.org/threads/guest-service-reshop-hell.3729/) — large backlogs at close.
- [r/Target: How does go-backs or reshop work at your store?](https://www.reddit.com/r/Target/comments/5okmwf/how_does_gobacks_or_reshop_work_at_your_store/)

## Not found (still assumptions)

No public source gave reliable numbers for reshop items per hour, seconds to scan or place an
item, or walking distances inside a store. These stay labeled `assumption` and should be measured
in the Stage 3 mock test before any real pilot.
