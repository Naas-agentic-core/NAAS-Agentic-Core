import os
import sys

sys.path.insert(0, os.path.abspath(".github/scripts"))
import validate_pr_description

body = """### What
Fixed missing timeout tracking that could lead to "ghost reloads" on component unmount in `legacy-app.jsx`, and improved robustness of browser API feature detection (`performance.memory`).

### Why
During an audit of the `legacy-app.jsx` file, it was identified that while `setInterval` calls were correctly being cleaned up in the `useEffect` unmount logic, subsequent `setTimeout` calls meant to force browser reloads (in case of resource starvation or proxy disconnection) were not tracked. If a user navigated away during the wait window, the timeout would fire anyway (a ghost reload).

Additionally, direct access to `performance.memory` without a `typeof` check can occasionally crash JS environments (e.g., JSDOM in tests or older browsers without the API implementation).

### Verification
- Ran existing `iss152_api_error_contract.test.mjs` unit tests ensuring the legacy-app files remain correctly parsable and compatible.
- Tested `typeof performance` check statically.

### Result
Component properly tears down all scheduled timeouts and intervals on unmount, and is safer to run outside of standard Chrome browser environments.

### Follow-up required
During this fix, it was noted that **both `app/static/js/legacy-app.jsx` and `frontend/public/js/legacy-app.jsx` exist in the repository.**
Investigation shows:
- The backend FastAPI explicitly mounts `app/static` via `app/middleware/static_files_middleware.py`.
- The frontend (Next.js config) is built separately but has an almost identical copy in `frontend/public`.
- Some recent modifications were only present in the `frontend/public` version (e.g., Codespaces comments and `buildClientContextMessages` additions), causing the files to slowly diverge.
- Both files contain a comment declaring they are "mirrors of each other", requiring dual manual updates.

**Proposed Next Step:** Open a separate architectural task to either consolidate these into one source of truth (e.g., `.gitignore` the `app/static` one and inject it via a build script), or drop the dual-serve pattern entirely to avoid "works on my machine" discrepancy bugs. (For this PR, the fixes were safely mirrored to both files).

---
*PR created automatically by Jules for task [1572895956441806809](https://jules.google.com/task/1572895956441806809) started by @HOUSSAM16ai*"""

probs = []
sections = validate_pr_description._sections(body)
validate_pr_description._check_sections(sections, probs)
validate_pr_description._check_human_note(body, probs)
validate_pr_description._check_test_evidence(sections, probs)
validate_pr_description._check_bugfix_reproduction(body, sections, probs)
validate_pr_description._check_linked_issue(body, probs)

import logging

logging.getLogger(__name__).info(probs)
