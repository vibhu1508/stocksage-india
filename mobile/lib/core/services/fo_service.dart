import '../models/fo_data.dart';
import 'api_service.dart';
import '../../config/api_config.dart';

class FOService {
  // Get the index option chain plus index futures
  static Future<NiftyData> getNiftyData(
    String? date, {
    String? symbol,
    String? expiry,
  }) async {
    final params = <String, String>{};
    if (date != null) params['target_date'] = date;
    if (symbol != null && symbol.isNotEmpty) params['symbol'] = symbol;
    if (expiry != null && expiry.isNotEmpty) params['expiry'] = expiry;

    final response = await ApiService.get(
      ApiConfig.foNifty,
      queryParams: params,
    );
    final data = ApiService.decodeResponse(response);
    return NiftyData.fromJson(data);
  }

  // Get futures analysis (momentum screener)
  static Future<Map<String, dynamic>> getFuturesAnalysis(
    String? date, {
    String? expiry,
  }) async {
    final params = <String, String>{};
    if (date != null) params['target_date'] = date;
    if (expiry != null && expiry.isNotEmpty) params['expiry_month'] = expiry;

    final response = await ApiService.get(
      ApiConfig.foFuturesAnalysis,
      queryParams: params,
    );
    return ApiService.decodeResponse(response);
  }

  // Get index (IDF) or stock (STF) futures contracts with their filter values
  static Future<FuturesTableData> getFuturesTable(
    String segment, {
    String? date,
    String? expiry,
    String? symbol,
  }) async {
    final params = <String, String>{'segment': segment};
    if (date != null) params['target_date'] = date;
    if (expiry != null && expiry.isNotEmpty) params['expiry'] = expiry;
    if (symbol != null && symbol.isNotEmpty) params['symbol'] = symbol;

    final response = await ApiService.get(
      ApiConfig.foFuturesTable,
      queryParams: params,
    );
    return FuturesTableData.fromJson(ApiService.decodeResponse(response));
  }

  // Get futures data for a symbol
  static Future<FOData> getFuturesData(String symbol, String? date) async {
    final params = <String, String>{};
    if (date != null) params['target_date'] = date;

    final response = await ApiService.get(
      ApiConfig.foFutures(symbol),
      queryParams: params,
    );
    final data = ApiService.decodeResponse(response);
    return FOData.fromJson(data);
  }

  // Get the option chain for a symbol
  static Future<OptionChainData> getOptionsData(
    String symbol,
    String? date, {
    String? expiry,
  }) async {
    final params = <String, String>{};
    if (date != null) params['target_date'] = date;
    if (expiry != null && expiry.isNotEmpty) params['expiry'] = expiry;

    final response = await ApiService.get(
      ApiConfig.foOptions(symbol),
      queryParams: params,
    );
    final data = ApiService.decodeResponse(response);
    return OptionChainData.fromJson(data);
  }
}
