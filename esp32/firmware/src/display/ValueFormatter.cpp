#include "ValueFormatter.h"

String ValueFormatter::format(const String& rawValue, const String& formatType)
{
    if (formatType.length() == 0 || rawValue == "--") return rawValue;

    if (formatType == "currency")    return formatCurrency(rawValue);
    if (formatType == "percent")     return formatPercent(rawValue);
    if (formatType == "number")      return formatNumber(rawValue);
    if (formatType == "temperature") return formatTemperature(rawValue);

    return rawValue;
}

String ValueFormatter::formatCurrency(const String& raw)
{
    double val = raw.toDouble();
    if (val == 0.0 && raw.indexOf('0') < 0) return raw;  // Not a valid number

    // For large values (>=1000), drop decimals
    // For small values, keep 2 decimals
    String intPart;
    if (val >= 1000.0 || val <= -1000.0) {
        intPart = String((long)val);
    } else {
        // Keep 2 decimals for small values
        char buf[20];
        snprintf(buf, sizeof(buf), "%.2f", val);
        String full(buf);
        int dot = full.indexOf('.');
        if (dot >= 0) {
            return "$" + addCommas(full.substring(0, dot)) + full.substring(dot);
        }
        intPart = full;
    }

    bool negative = intPart.startsWith("-");
    if (negative) intPart = intPart.substring(1);

    String result = "$" + addCommas(intPart);
    if (negative) result = "-" + result;
    return result;
}

String ValueFormatter::formatPercent(const String& raw)
{
    double val = raw.toDouble();
    char buf[16];
    snprintf(buf, sizeof(buf), "%.1f%%", val);
    return String(buf);
}

String ValueFormatter::formatNumber(const String& raw)
{
    double val = raw.toDouble();
    String intPart = String((long)val);
    bool negative = intPart.startsWith("-");
    if (negative) intPart = intPart.substring(1);

    String result = addCommas(intPart);
    if (negative) result = "-" + result;
    return result;
}

String ValueFormatter::formatTemperature(const String& raw)
{
    double val = raw.toDouble();
    char buf[16];
    snprintf(buf, sizeof(buf), "%.1fF", val);
    return String(buf);
}

String ValueFormatter::addCommas(const String& integerPart)
{
    int len = integerPart.length();
    if (len <= 3) return integerPart;

    String result;
    int firstGroup = len % 3;
    if (firstGroup == 0) firstGroup = 3;

    result = integerPart.substring(0, firstGroup);
    for (int i = firstGroup; i < len; i += 3) {
        result += ",";
        result += integerPart.substring(i, i + 3);
    }
    return result;
}
