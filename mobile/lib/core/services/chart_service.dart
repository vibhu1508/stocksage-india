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

  Future<Map<String, dynamic>> getFundamentals(String symbol) async {
    final response = await ApiService.get(
      '${ApiConfig.apiUrl}/charts/fundamentals?symbol=$symbol',
    );
    if (response.statusCode == 200) {
      return json.decode(response.body);
    }
    throw Exception('Failed to load fundamentals');
  }

  Future<Map<String, dynamic>> getFinancials(
    String symbol, {
    String statement = 'results',
  }) async {
    final response = await ApiService.get(
      '${ApiConfig.apiUrl}/charts/financials?symbol=$symbol&statement=$statement',
    );
    if (response.statusCode == 200) {
      return json.decode(response.body);
    }
    throw Exception('Failed to load financials');
  }

  Future<Map<String, dynamic>> getNews(String symbol) async {
    final response = await ApiService.get(
      '${ApiConfig.apiUrl}/charts/news?symbol=$symbol',
    );
    if (response.statusCode == 200) {
      return json.decode(response.body);
    }
    throw Exception('Failed to load news');
  }

  Future<Map<String, dynamic>> getOptionDates(String symbol) async {
    final response = await ApiService.get(
      '${ApiConfig.apiUrl}/charts/options/dates?symbol=$symbol',
    );
    if (response.statusCode == 200) {
      return json.decode(response.body);
    }
    throw Exception('Failed to load option dates');
  }

  Future<Map<String, dynamic>> getOptionChain(
    String symbol,
    String date,
  ) async {
    final response = await ApiService.get(
      '${ApiConfig.apiUrl}/charts/options/chain?symbol=$symbol&date=$date',
    );
    if (response.statusCode == 200) {
      return json.decode(response.body);
    }
    throw Exception('Failed to load option chain');
  }
}
