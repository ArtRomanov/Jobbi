"""The conversations of the CV chat eval: typical user comments.

Each scenario starts from its CV (the Markdown fixture unless it names the
plain-text one) on a fresh database. All cards of
every turn are accepted ("Accept all"), then the requests are checked on the
final CV.
"""

from evals.cv_chat.fixtures import PLAIN_CV, PROFILE_TEXT
from evals.cv_chat.scoring import Check, Request, Scenario, Turn

_KEEP_ALL = Check("sections_kept")
# Backlog #27: the CV keeps its sections, entries and bullet shape.
_STRUCTURE = (
    Request("sections kept", (_KEEP_ALL,)),
    Request("entries kept", (Check("h3_unchanged"),)),
    Request("action-result-scope bullets kept", (Check("ars_kept"),)),
)

# The structure scenarios of backlog #27, small enough to run on their own
# (pass them to `--only`).
STRUCTURE_SCENARIO_IDS = (
    "adapt",
    "shorten_all",
    "remove_section",
    "structure_plain",
    "russian_adapt",
)

SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        id="adapt",
        turns=(Turn("Adapt my CV to this vacancy"),),
        requests=_STRUCTURE,
    ),
    Scenario(
        id="shorten_all",
        turns=(Turn("Shorten the whole CV"),),
        requests=(Request("shorter", (Check("shorter"),)), *_STRUCTURE),
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
            Request("nothing else changed", (Check("only_removed", "CERTIFICATIONS"),)),
        ),
    ),
    Scenario(
        id="structure_plain",
        cv=PLAIN_CV,
        turns=(Turn("Structure my CV"),),
        requests=(
            Request("header and sections", (Check("min_sections", "4"),)),
            Request("wording unchanged", (Check("wording_kept"),)),
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
    # Backlog #34: a whole draft from the reply text goes in as one
    # replace_all card.
    Scenario(
        id="whole_draft",
        turns=(
            Turn(
                "Write a shorter, 2-page version of my CV here as text. Do not "
                "change the CV yet.",
                expects_change=False,
            ),
            Turn("Apply the whole draft to the CV."),
        ),
        requests=(Request("shorter", (Check("shorter"),)), *_STRUCTURE),
    ),
    Scenario(
        id="russian_adapt",
        turns=(Turn("Адаптируй моё CV под эту вакансию"),),
        requests=(
            *_STRUCTURE,
            Request("reply in Russian", (Check("reply_cyrillic"),)),
            Request("CV stays English", (Check("cv_no_cyrillic"),)),
        ),
    ),
)
