import Foundation

struct APIEndpoint: Identifiable, Codable {
    var id: UUID = UUID()
    var name: String
    var url: String
    var headers: [String: String]
    var authToken: String
    var pollIntervalSeconds: Int
    var jsonPaths: [String: String]
    var enabled: Bool
}

enum APITemplate {
    static let weatherAPI = APIEndpoint(
        name: "OpenWeatherMap",
        url: "https://api.openweathermap.org/data/2.5/weather?q=London&appid=YOUR_KEY&units=metric",
        headers: ["Accept": "application/json"],
        authToken: "",
        pollIntervalSeconds: 300,
        jsonPaths: [
            "temperature": "$.main.temp",
            "humidity": "$.main.humidity",
            "description": "$.weather[0].description"
        ],
        enabled: false
    )

    static let cryptoAPI = APIEndpoint(
        name: "CoinGecko BTC",
        url: "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd",
        headers: ["Accept": "application/json"],
        authToken: "",
        pollIntervalSeconds: 60,
        jsonPaths: [
            "btc_usd": "$.bitcoin.usd"
        ],
        enabled: true
    )

    static let all: [APIEndpoint] = [weatherAPI, cryptoAPI]
}
