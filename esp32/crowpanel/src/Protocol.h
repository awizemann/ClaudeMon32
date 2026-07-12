// Serial JSON protocol handler for the CrowPanel Cockpit. Parses one command
// line and returns the response string to write back. Same framing/response
// rules as the e-paper firmware (see ../../docs/protocol.md): reply echoes the
// cmd; errors carry no cmd; the reply is emitted BEFORE the (deferred) LVGL
// redraw. This is the ONLY writer of the Dashboard model (the ingestion seam);
// the UI reads it exclusively through ui_update().
#pragma once

#include <Arduino.h>
#include <ArduinoJson.h>
#include "Dashboard.h"

class Protocol {
public:
    // Handle one JSON line. If it was a set_cockpit, `out` is populated and
    // `dashboardUpdated` is set true (the caller flips a pending-render flag and
    // renders on the main loop AFTER writing the reply). Returns the reply JSON.
    static String handle(const String& line, Dashboard& out, bool& dashboardUpdated);

private:
    static String parseCockpit(const JsonObjectConst& params, Dashboard& out);
    static String makeOk(const char* cmd, const char* msg);
    static String makeError(const char* msg);
};
