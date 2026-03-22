import '../models/fo_data.dart';
import 'api_service.dart';
import '../../config/api_config.dart';

class FOService {
  // Get NIFTY data
  static Future<NiftyData> getNiftyData(String? date) async {
    final params = <String, String>{};
    if (date != null) params['target_date'] = date;

    final response = await ApiService.get(
      ApiConfig.foNifty,
      queryParams: params,
    );
    final data = ApiService.decodeResponse(response);
    return NiftyData.fromJson(data);
  }

  // Get futures analysis
  static Future<Map<String, dynamic>> getFuturesAnalysis(String? date, [String? expiryMonth]) async {
    final params = <String, String>{};
    if (date != null) params['target_date'] = date;
    if (expiryMonth != null && expiryMonth.isNotEmpty) {
      params['expiry_month'] = expiryMonth;
    }

    final response = await ApiService.get(
      ApiConfig.foFuturesAnalysis,
      queryParams: params,
    );
    return ApiService.decodeResponse(response);
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

  // Get options data for a symbol
  static Future<FOData> getOptionsData(
    String symbol,
    String? date,
    String? optionType,
  ) async {
    final params = <String, String>{};
    if (date != null) params['target_date'] = date;
    if (optionType != null && optionType.isNotEmpty) {
      params['option_type'] = optionType;
    }

    final response = await ApiService.get(
      ApiConfig.foOptions(symbol),
      queryParams: params,
    );
    final data = ApiService.decodeResponse(response);
    return FOData.fromJson(data);
  }
}
