import { http, HttpResponse } from "msw";
import type { Cv } from "@/entities/cv";
import { server } from "../setup";
import { makeMockCv, mockCvs } from "./handlers";

export interface CvStore {
  /** The CVs as the server holds them now. */
  current: () => Cv[];
  /** Bodies of every `POST /cvs`. */
  posts: Record<string, unknown>[];
  /** Bodies of every `PATCH /cvs/:id`. */
  patches: Record<string, unknown>[];
}

/**
 * A tiny in-memory CVs API: create and save change what `GET /cvs` returns
 * next, and only one CV is the base at a time — like the real server. Lets a
 * test save in the editor, land on the CVs page and see the fresh list.
 */
export function serveCvStore(initial: readonly Cv[] = mockCvs): CvStore {
  let cvs: Cv[] = initial.map((cv) => ({ ...cv }));
  const posts: Record<string, unknown>[] = [];
  const patches: Record<string, unknown>[] = [];

  function setBase(id: string): void {
    cvs = cvs.map((cv) => ({ ...cv, is_base: cv.id === id }));
  }

  server.use(
    http.get("*/api/v1/cvs", () => HttpResponse.json(cvs)),
    http.get("*/api/v1/cvs/:id", ({ params }) => {
      const cv = cvs.find((c) => c.id === params.id);
      return cv ? HttpResponse.json(cv) : HttpResponse.json({ detail: "Not found" }, { status: 404 });
    }),
    http.post("*/api/v1/cvs", async ({ request }) => {
      const body = (await request.json()) as { name: string; content: string; is_base?: boolean };
      posts.push(body);
      const created = makeMockCv({ id: "cv-new", name: body.name, content: body.content });
      cvs = [...cvs, created];
      if (body.is_base === true) setBase(created.id);
      return HttpResponse.json(cvs.find((c) => c.id === created.id), { status: 201 });
    }),
    http.patch("*/api/v1/cvs/:id", async ({ params, request }) => {
      const body = (await request.json()) as Record<string, unknown> & { version: number };
      patches.push(body);
      const { version, is_base: isBase, ...changes } = body;
      cvs = cvs.map((cv) => (cv.id === params.id ? { ...cv, ...changes, version: version + 1 } : cv));
      if (isBase === true) setBase(params.id as string);
      if (isBase === false) {
        cvs = cvs.map((cv) => (cv.id === params.id ? { ...cv, is_base: false } : cv));
      }
      return HttpResponse.json(cvs.find((c) => c.id === params.id));
    }),
  );

  return { current: () => cvs, posts, patches };
}
