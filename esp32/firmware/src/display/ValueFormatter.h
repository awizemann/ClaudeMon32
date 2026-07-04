#ifndef VALUE_FORMATTER_H
#define VALUE_FORMATTER_H

#include <Arduino.h>

class ValueFormatter {
public:
    // Format a raw numeric string according to the format type.
    // "currency"    -> "$87,432"
    // "percent"     -> "87.4%"
    // "number"      -> "87,432"
    // "temperature" -> "72.3F"
    // ""            -> pass-through
    static String format(const String& rawValue, const String& formatType);

private:
    static String formatCurrency(const String& raw);
    static String formatPercent(const String& raw);
    static String formatNumber(const String& raw);
    static String formatTemperature(const String& raw);
    static String addCommas(const String& integerPart);
};

#endif // VALUE_FORMATTER_H
