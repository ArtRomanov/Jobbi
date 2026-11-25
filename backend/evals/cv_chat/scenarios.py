"""The conversations of the CV chat eval: typical user comments.

Each scenario starts from the fixture CV on a fresh database. All cards of
every turn are accepted ("Accept all"), then the requests are checked on the
final CV.
"""

from evals.cv_chat.fixtures import PROFILE_TEXT
from evals.cv_chat.scoring import Check, Request, Scenario, Turn

_KEEP_ALL = Check("sections_kept")

SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        id="adapt",
        turns=(Turn("Adapt my CV to this vacancy"),),
        requests=(
            Request("sections kept", (_KEEP_ALL,)),
            Request("entries kept", (Check("h3_unchanged"),)),
        ),
    ),
    Scenario(
        id="shorter_react",
        turns=(Turn("Make it shorter and focus on React"),),
        requests=(
            Request("shorter", (Check("shorter"),)),
            Request("sections kept", (_KEEP_ALL,)),
        ),
    ),
    Scenario(
        id="three_requests",
        turns=(
            Turn(
                "Add Next.js to my skills, rephrase the profile to mention that I "
                "work remotely, and remove the second bullet at Northwind Pay."
            ),
        ),
        requests=(
            Request("Next.js in skills", (Check("present", "Next.js", "SKILLS"),)),
            Request(
                "profile mentions remote",
                (
                    Check("present", "remote", "PROFILE"),
                    Check("absent", PROFILE_TEXT),
                ),
            ),
            Request(
                "2nd Northwind bullet removed",
                (Check("absent", "Introduced a shared design system"),),
            ),
        ),
    ),
    Scenario(
        id="own_words",
        turns=(
            Turn(
                "Replace the Bluefin bullet about mentoring with exactly this: "
                "- **Mentored four junior developers:** two were promoted within "
                "a year. **Scope:** weekly 1:1s."
            ),
        ),
        requests=(
            Request(
                "user's wording used",
                (
                    Check(
                        "present",
                        "- **Mentored four junior developers:** two were promoted "
                        "within a year. **Scope:** weekly 1:1s.",
                    ),
                    Check("absent", "**Mentored junior developers:**"),
                ),
            ),
        ),
    ),
    Scenario(
        id="remove_section",
        turns=(Turn("Remove the CERTIFICATIONS section."),),
        requests=(
            Request(
                "section removed",
                (
                    Check("absent", "## CERTIFICATIONS"),
                    Check("absent", "AWS Certified Cloud Practitioner"),
                ),
            ),
            Request("other sections kept", (Check("sections_kept", "CERTIFICATIONS"),)),
        ),
    ),
    Scenario(
        id="cannot_do",
        turns=(
            Turn(
                "Add the job I had before Bluefin Retail to the experience section.",
                expects_change=False,
            ),
        ),
        requests=(
            Request("no invented job", (Check("h3_unchanged"),)),
            Request("asks or explains", (Check("reply_asks_or_explains"),)),
        ),
    ),
    Scenario(
        id="followup_revert",
        turns=(
            Turn(
                "Rewrite my profile so it focuses on React and data-heavy dashboards."
            ),
            Turn("No, keep the old wording for the profile."),
        ),
        requests=(Request("old profile back", (Check("present", PROFILE_TEXT),)),),
    ),
    Scenario(
        id="russian",
        turns=(Turn("Убери Vue 3 из навыков и сделай профиль короче."),),
        requests=(
            Request("Vue 3 out of skills", (Check("absent", "Vue 3", "SKILLS"),)),
            Request("profile shorter", (Check("shorter", section="PROFILE"),)),
            Request(
                "Vue 3 kept in experience",
                (Check("present", "Vue 3", "EXPERIENCE"),),
            ),
            Request("reply in Russian", (Check("reply_cyrillic"),)),
            Request("CV stays English", (Check("cv_no_cyrillic"),)),
        ),
    ),
)
