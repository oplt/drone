import { useState } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { LabelingConflictDialog } from "./LabelingConflictDialog";

describe("LabelingConflictDialog", () => {
  it("labels the modal, focuses the safe action, and returns focus after resolution", async () => {
    const user = userEvent.setup();

    function Harness() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button type="button" onClick={() => setOpen(true)}>
            Save annotations
          </button>
          <LabelingConflictDialog
            open={open}
            message="The annotation revision changed."
            expectedRevision={2}
            currentRevision={4}
            onReload={() => setOpen(false)}
            onDownload={vi.fn()}
            onOverwrite={vi.fn()}
          />
        </>
      );
    }

    render(<Harness />);
    const trigger = screen.getByRole("button", { name: "Save annotations" });
    await user.click(trigger);

    expect(
      screen.getByRole("dialog", { name: "Annotation revision conflict" }),
    ).toHaveAccessibleDescription(
      /draft used revision 2.*server is now revision 4/i,
    );
    const reload = screen.getByRole("button", {
      name: "Reload server version",
    });
    await waitFor(() => expect(reload).toHaveFocus());
    await user.keyboard("{Enter}");

    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it("exposes keyboard-operable download and overwrite resolutions", async () => {
    const user = userEvent.setup();
    const download = vi.fn();
    const overwrite = vi.fn();
    render(
      <LabelingConflictDialog
        open
        message="Conflict."
        expectedRevision={1}
        currentRevision={2}
        onReload={vi.fn()}
        onDownload={download}
        onOverwrite={overwrite}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Download local copy" }));
    await user.click(
      screen.getByRole("button", { name: "Overwrite with my draft" }),
    );

    expect(download).toHaveBeenCalledOnce();
    expect(overwrite).toHaveBeenCalledOnce();
  });
});
