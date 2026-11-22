import type { components, operations } from "@/shared/api";

/** One Inbox card. */
export type Vacancy = components["schemas"]["VacancyRead"];

/** A source shown on a card: stable `key` ("<kind>:<handle>") + display `label`. */
export type VacancyCardSource = Vacancy["sources"][number];

/** AI fit rating: "high" | "medium" | "low". */
export type VacancyFit = NonNullable<Vacancy["fit"]>;

/** "new" until the user acts on the card, then "seen". */
export type VacancyState = Vacancy["state"];

/** Response of GET /api/v1/vacancies. */
export type VacancyPage = components["schemas"]["PaginatedResponse_VacancyRead_"];

/** Response of GET /api/v1/vacancies/new-count. */
export type VacancyNewCount = components["schemas"]["NewVacancyCount"];

/**
 * Query of GET /api/v1/vacancies; omitted fields use the server defaults.
 * `source` is a source KEY ("<kind>:<handle>"), never a label.
 */
export type VacancyListParams = NonNullable<
  operations["get_vacancies_api_v1_vacancies_get"]["parameters"]["query"]
>;

/** An application that already tracks the card's job link (`existing_application` on a card). */
export type ExistingApplicationRef = components["schemas"]["ExistingApplicationRef"];

/** Body of POST /api/v1/vacancies/{id}/add-to-tracker. */
export type AddToTrackerRequest = components["schemas"]["AddToTrackerRequest"];

/** 201 of add-to-tracker: the new application, plus the CV copy when `base_cv_id` was sent. */
export type AddToTrackerResponse = components["schemas"]["AddToTrackerResponse"];

/** Structured 409 of add-to-tracker when the job link is tracked and `allow_duplicate` is false. */
export type DuplicateApplicationConflict = components["schemas"]["DuplicateApplicationConflict"];
