import { http, HttpResponse } from "msw";
import { listVacancies } from "@/entities/vacancy";
import type { Vacancy } from "@/entities/vacancy";
import type { VacancySource, VacancySourcesResponse } from "@/entities/vacancy-source";
import { mockVacancy, mockVacancyPageEmpty, mockVacancySource, mockVacancySourcesEmpty } from "./mocks/handlers";
import { server } from "./setup";

// Compile-time drift check: the mocks must match the generated API types
const typedVacancy: Vacancy = mockVacancy;
const typedSource: VacancySource = mockVacancySource;
const typedSources: VacancySourcesResponse = mockVacancySourcesEmpty;

describe("listVacancies", () => {
  it("mocks match the generated types", () => {
    expect([typedVacancy, typedSource, typedSources]).toHaveLength(3);
  });

  it("filters by source key and passes the other params", async () => {
    let query: URLSearchParams | null = null;
    server.use(
      http.get("*/api/v1/vacancies", ({ request }) => {
        query = new URL(request.url).searchParams;
        return HttpResponse.json(mockVacancyPageEmpty);
      }),
    );

    await listVacancies({
      source: "telegram:frontend_jobs",
      state: "new",
      sort: "fit",
      page: 2,
      per_page: 20,
    });

    expect(Object.fromEntries(query!)).toEqual({
      source: "telegram:frontend_jobs",
      state: "new",
      sort: "fit",
      page: "2",
      per_page: "20",
    });
  });

  it("sends no query when no params are given", async () => {
    let search = "unset";
    server.use(
      http.get("*/api/v1/vacancies", ({ request }) => {
        search = new URL(request.url).search;
        return HttpResponse.json(mockVacancyPageEmpty);
      }),
    );

    await listVacancies();

    expect(search).toBe("");
  });
});
