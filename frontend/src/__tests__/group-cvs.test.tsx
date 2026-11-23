import { render, screen, within } from "@testing-library/react";
import { buildCvSelectChoices, formatTailoredFor, groupCvs } from "@/entities/cv";
import { FormSelect } from "@/shared/ui";
import { makeMockCv } from "./mocks/handlers";

const base = makeMockCv({ id: "b", name: "Base", is_base: true, updated_at: "2026-01-01T00:00:00Z" });
const ownOld = makeMockCv({ id: "o1", name: "Own old", updated_at: "2026-02-01T00:00:00Z" });
const ownNew = makeMockCv({ id: "o2", name: "Own new", updated_at: "2026-03-01T00:00:00Z" });
const copyOld = makeMockCv({ id: "t1", name: "Copy old", kind: "tailored", updated_at: "2026-02-10T00:00:00Z" });
const copyNew = makeMockCv({ id: "t2", name: "Copy new", kind: "tailored", updated_at: "2026-04-01T00:00:00Z" });

describe("groupCvs", () => {
  it("puts the base first, then own CVs and tailored copies, each newest first", () => {
    const grouped = groupCvs([copyOld, ownOld, copyNew, base, ownNew]);
    expect(grouped.base?.id).toBe("b");
    expect(grouped.own.map((cv) => cv.id)).toEqual(["b", "o2", "o1"]);
    expect(grouped.tailored.map((cv) => cv.id)).toEqual(["t2", "t1"]);
  });

  it("has no base when none is marked", () => {
    const grouped = groupCvs([ownOld, copyOld]);
    expect(grouped.base).toBeNull();
    expect(grouped.own.map((cv) => cv.id)).toEqual(["o1"]);
  });

  it("treats a base with kind tailored as own", () => {
    const promoted = makeMockCv({ id: "p", name: "P", is_base: true, kind: "tailored" });
    expect(groupCvs([promoted]).tailored).toEqual([]);
  });
});

describe("buildCvSelectChoices", () => {
  it("labels the base and groups tailored copies", () => {
    expect(buildCvSelectChoices([copyOld, ownOld, base])).toEqual({
      options: [
        { value: "b", label: "Base (base)" },
        { value: "o1", label: "Own old" },
      ],
      groups: [{ label: "Tailored copies", options: [{ value: "t1", label: "Copy old" }] }],
    });
  });

  it("has no group without tailored copies", () => {
    expect(buildCvSelectChoices([ownOld]).groups).toEqual([]);
  });
});

describe("formatTailoredFor", () => {
  it("joins company and role, leaving out an empty part", () => {
    expect(formatTailoredFor({ application_id: "a", company_name: "Acme", role_title: "Dev" })).toBe(
      "Acme — Dev",
    );
    expect(formatTailoredFor({ application_id: "a", company_name: "", role_title: "Dev" })).toBe("Dev");
  });
});

describe("FormSelect groups", () => {
  it("renders plain options as before when no groups are given", () => {
    render(<FormSelect label="Pick" options={[{ value: "a", label: "A" }]} />);
    const select = screen.getByRole("combobox", { name: "Pick" });
    expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual(["A"]);
    expect(select.querySelector("optgroup")).toBeNull();
  });

  it("renders groups as optgroups after the plain options and skips empty groups", () => {
    render(
      <FormSelect
        label="Pick"
        options={[{ value: "a", label: "A" }]}
        groups={[
          { label: "More", options: [{ value: "b", label: "B" }] },
          { label: "Empty", options: [] },
        ]}
      />,
    );
    const select = screen.getByRole("combobox", { name: "Pick" });
    const groups = select.querySelectorAll("optgroup");
    expect(groups).toHaveLength(1);
    expect(groups[0]).toHaveAttribute("label", "More");
    expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual(["A", "B"]);
  });
});

describe("FormSelect aria-describedby", () => {
  it("keeps the caller's description together with the error", () => {
    render(
      <>
        <p id="hint">Hint</p>
        <FormSelect label="Pick" id="pick" options={[]} aria-describedby="hint" error="Required" />
      </>,
    );
    expect(screen.getByRole("combobox", { name: "Pick" })).toHaveAttribute(
      "aria-describedby",
      "hint pick-error",
    );
  });

  it("uses only the caller's description without an error, and none by default", () => {
    const { rerender } = render(<FormSelect label="Pick" options={[]} aria-describedby="hint" />);
    expect(screen.getByRole("combobox", { name: "Pick" })).toHaveAttribute("aria-describedby", "hint");
    rerender(<FormSelect label="Pick" options={[]} />);
    expect(screen.getByRole("combobox", { name: "Pick" })).not.toHaveAttribute("aria-describedby");
  });
});
