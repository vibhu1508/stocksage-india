import 'dart:convert';
import 'api_service.dart';
import '../../config/api_config.dart';

class ChartService {
  Future<Map<String, dynamic>> searchTickers(String query) async {
    final response = await ApiService.get(
      '${ApiConfig.apiUrl}/charts/search?q=$query',
    );
    if (response.statusCode == 200) {
      return json.decode(response.body);
    }
    throw Exception('Failed to search tickers');
  }

  Future<Map<String, dynamic>> getQuote(String symbol) async {
    final response = await ApiService.get(
      '${ApiConfig.apiUrl}/charts/quote?symbol=$symbol',
    );
    if (response.statusCode == 200) {
      return json.decode(response.body);
    }
    throw Exception('Failed to get quote');
  }

  Future<Map<String, dynamic>> getHistory(
    String symbol,
    String period,
    String interval,
  ) async {
    final response = await ApiService.get(
      '${ApiConfig.apiUrl}/charts/history?symbol=$symbol&period=$period&interval=$interval',
    );
    if (response.statusCode == 200) {
      return json.decode(response.body);
    }
    throw Exception('Failed to load chart data');
  }
}
