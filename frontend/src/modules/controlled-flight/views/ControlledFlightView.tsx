import { useControlledFlightPageSession } from "../hooks/useControlledFlightPageSession";
import { ControlledFlightPageDrawersSection } from "../sections/ControlledFlightPageDrawersSection";
import { ControlledFlightPageMainSection } from "../sections/ControlledFlightPageMainSection";

export function ControlledFlightView() {
  const session = useControlledFlightPageSession();

  return (
    <>
      <ControlledFlightPageMainSection session={session} />
      <ControlledFlightPageDrawersSection session={session} />
    </>
  );
}
