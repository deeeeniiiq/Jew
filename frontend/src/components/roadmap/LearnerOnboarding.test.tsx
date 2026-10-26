// @vitest-environment jsdom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { expect, it, vi } from "vitest";
import { EMPTY_LEARNER_PROFILE, LearnerOnboarding, needsLearnerOnboarding } from "./LearnerOnboarding";

it("shows onboarding once for a fresh demo workspace and respects legacy work", () => {
  expect(needsLearnerOnboarding(EMPTY_LEARNER_PROFILE, 1)).toBe(true);
  expect(needsLearnerOnboarding({ ...EMPTY_LEARNER_PROFILE, onboarding_complete: true }, 2)).toBe(false);
  expect(needsLearnerOnboarding(EMPTY_LEARNER_PROFILE, 4)).toBe(false);
});

it("saves the first learning profile with its study preferences", async () => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  const container = document.createElement("div");
  const root = createRoot(container);
  const onSave = vi.fn(async () => {});
  try {
    await act(async () => root.render(<LearnerOnboarding profile={EMPTY_LEARNER_PROFILE} onSave={onSave} />));
    expect(container.textContent).not.toContain("Cancelar");
    const buttons = [...container.querySelectorAll("button")];
    await act(async () => buttons.find((button) => button.textContent?.includes("Biologia"))?.click());
    await act(async () => buttons.find((button) => button.textContent?.includes("Leitura guiada"))?.click());
    const hours = container.querySelector<HTMLInputElement>('input[type="number"]');
    expect(hours).not.toBeNull();
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set?.call(hours, "5");
      hours?.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => container.querySelector<HTMLFormElement>("form")?.requestSubmit());
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
      profession: "Biologia", study_hours_per_week: 5,
      learning_preferences: ["Leitura guiada"], onboarding_complete: true,
    }));
  } finally {
    await act(async () => root.unmount());
    vi.unstubAllGlobals();
  }
});
