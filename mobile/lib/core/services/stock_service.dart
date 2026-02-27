import '../models/stock.dart';
import 'api_service.dart';
import '../../config/api_config.dart';

class StockService {
  // Get available symbols
  static Future<List<String>> getSymbols() async {
    final response = await ApiService.get(ApiConfig.stockSymbols);
    final data = ApiService.decodeResponse(response);
    return List<String>.from(data['symbols'] ?? []);
  }

  // Search symbols
  static Future<List<SymbolSearchResult>> searchSymbols(
    String query,
    int limit,
  ) async {
    final response = await ApiService.get(
      ApiConfig.stockSearch,
      queryParams: {'q': query, 'limit': limit.toString()},
    );
    final data = ApiService.decodeResponse(response);
    return (data['results'] as List? ?? [])
        .map((e) => SymbolSearchResult.fromJson(e))
        .toList();
  }

  // Compare stocks
  static Future<StockComparison> compareStocks(
    String date1,
    String date2,
    String? symbols,
  ) async {
    final params = <String, String>{'date1': date1, 'date2': date2};
    if (symbols != null && symbols.isNotEmpty) {
      params['symbols'] = symbols;
    }

    final response = await ApiService.get(
      ApiConfig.stockCompare,
      queryParams: params,
    );
    final data = ApiService.decodeResponse(response);
    return StockComparison.fromJson(data);
  }
}
