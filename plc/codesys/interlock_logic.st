(* ============================================================================
   PRG_InterlockLogic
   CODESYS Structured Text - Allen-Bradley / generic IEC 61131-3 target
   Smart Factory Digital Twin - Safety zone management and robotic cell
   interlocking, complementary to FB_ConveyorSequencing (TIA Portal/Siemens)

   Implements a hardware-style safety interlock chain per ISO 10218 /
   IEC 62061: E-stop, light curtain, robot cell door, and reject-arm
   air-pressure interlocks all gate the master "PermissiveOK" signal that
   both the conveyor and robot cell logic must read before running.
   ============================================================================ *)

PROGRAM PRG_InterlockLogic

VAR
    (* --- Physical safety inputs --- *)
    EStop_Pushbutton_NC    : BOOL;  (* Normally-closed, TRUE = healthy/not pressed *)
    LightCurtain_Clear      : BOOL;  (* TRUE = beam unbroken, zone clear *)
    RobotCellDoor_Closed    : BOOL;  (* TRUE = door closed and latched *)
    RejectArm_AirPressureOK : BOOL;  (* TRUE = pneumatic supply within range *)

    (* --- Reset / acknowledge from SCADA (Ignition) --- *)
    FaultReset_Command      : BOOL;

    (* --- Outputs consumed by conveyor/robot sequencing logic --- *)
    PermissiveOK            : BOOL;  (* Master permissive: TRUE = safe to run *)
    SafetyFaultActive        : BOOL;
    SafetyFaultCode          : INT;   (* 0=none 1=estop 2=curtain 3=door 4=air pressure *)

    (* --- Latching fault memory (must be manually reset) --- *)
    faultLatched             : BOOL := FALSE;
    lastFaultCode            : INT := 0;

    (* --- Diagnostics timers --- *)
    tonFaultDebounce         : TON;
    debounceDone             : BOOL;
END_VAR

(* ----------------------------------------------------------------------
   Step 1: Evaluate raw safety conditions with a short debounce to avoid
   nuisance trips from sensor noise/simulation jitter.
   ---------------------------------------------------------------------- *)
tonFaultDebounce(
    IN := NOT (EStop_Pushbutton_NC AND LightCurtain_Clear AND
               RobotCellDoor_Closed AND RejectArm_AirPressureOK),
    PT := T#50MS
);
debounceDone := tonFaultDebounce.Q;

(* ----------------------------------------------------------------------
   Step 2: Determine fault code (priority order matches typical safety
   category assignment: E-stop first, then perimeter guarding).
   ---------------------------------------------------------------------- *)
IF debounceDone THEN
    IF NOT EStop_Pushbutton_NC THEN
        lastFaultCode := 1;
    ELSIF NOT LightCurtain_Clear THEN
        lastFaultCode := 2;
    ELSIF NOT RobotCellDoor_Closed THEN
        lastFaultCode := 3;
    ELSIF NOT RejectArm_AirPressureOK THEN
        lastFaultCode := 4;
    ELSE
        lastFaultCode := 0;
    END_IF;

    IF lastFaultCode <> 0 THEN
        faultLatched := TRUE;
    END_IF;
END_IF;

(* ----------------------------------------------------------------------
   Step 3: Latched fault requires explicit operator reset from SCADA,
   and only clears if the underlying condition is actually healthy again.
   ---------------------------------------------------------------------- *)
IF FaultReset_Command AND
   EStop_Pushbutton_NC AND LightCurtain_Clear AND
   RobotCellDoor_Closed AND RejectArm_AirPressureOK THEN
    faultLatched := FALSE;
    lastFaultCode := 0;
END_IF;

(* ----------------------------------------------------------------------
   Step 4: Drive outputs consumed by conveyor sequencing (FB_ConveyorSequencing)
   and the ROS2/robot-cell bridge.
   ---------------------------------------------------------------------- *)
SafetyFaultActive := faultLatched;
SafetyFaultCode   := lastFaultCode;
PermissiveOK      := NOT faultLatched AND
                      EStop_Pushbutton_NC AND LightCurtain_Clear AND
                      RobotCellDoor_Closed AND RejectArm_AirPressureOK;

END_PROGRAM
