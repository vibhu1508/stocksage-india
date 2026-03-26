import 'dart:convert';

import '../../config/api_config.dart';
import '../../core/services/api_service.dart';

class PortfolioHolding {
  final int id;
  final String symbol;
  final String instrumentType;
  final int qty;
  final int lots;
  final int lotSize;
  final double avgPrice;
  final double invested;
  final String? expiry;
  final double? strike;
  final String? optionType;
  final String? action;
  final String? notes;

  PortfolioHolding({
    required this.id,
    required this.symbol,
    required this.instrumentType,
    required this.qty,
    required this.lots,
    required this.lotSize,
    required this.avgPrice,
    required this.invested,
    this.expiry,
    this.strike,
    this.optionType,
    this.action,
    this.notes,
  });

  factory PortfolioHolding.fromJson(Map<String, dynamic> json) {
    return PortfolioHolding(
      id: json['id'] as int,
      symbol: (json['symbol'] ?? '').toString(),
      instrumentType: (json['instrument_type'] ?? 'EQUITY').toString(),
      qty: (json['qty'] ?? 0) as int,
      lots: (json['lots'] ?? 0) as int,
      lotSize: (json['lot_size'] ?? 1) as int,
      avgPrice: (json['avg_price'] as num?)?.toDouble() ?? 0,
      invested: (json['invested'] as num?)?.toDouble() ?? 0,
      expiry: json['expiry']?.toString(),
      strike: (json['strike'] as num?)?.toDouble(),
      optionType: json['option_type']?.toString(),
      action: json['action']?.toString(),
      notes: json['notes']?.toString(),
    );
  }
}

class PortfolioSymbolSuggestion {
  final String symbol;
  final String name;
  final String series;
  final List<String> allowedInstruments;

  PortfolioSymbolSuggestion({
    required this.symbol,
    required this.name,
    required this.series,
    required this.allowedInstruments,
  });

  factory PortfolioSymbolSuggestion.fromJson(Map<String, dynamic> json) {
    final allowed = (json['allowed_instruments'] as List? ?? const [])
        .map((e) => e.toString().toUpperCase())
        .toList();

    return PortfolioSymbolSuggestion(
      symbol: (json['symbol'] ?? '').toString().toUpperCase(),
      name: (json['name'] ?? '').toString(),
      series: (json['series'] ?? '').toString().toUpperCase(),
      allowedInstruments: allowed,
    );
  }
}

class DerivativeContractsData {
  final List<String> expiries;
  final List<double> strikes;
  final String? selectedExpiry;

  DerivativeContractsData({
    required this.expiries,
    required this.strikes,
    required this.selectedExpiry,
  });
}

class PortfolioService {
  Future<Map<String, dynamic>> getHoldings() async {
    final res = await ApiService.get(ApiConfig.portfolioHoldings);
    if (res.statusCode != 200) {
      throw Exception('Unable to load portfolio holdings');
    }

    final data = jsonDecode(res.body) as Map<String, dynamic>;
    final holdingsRaw = (data['holdings'] as List? ?? []);
    final holdings = holdingsRaw
        .whereType<Map<String, dynamic>>()
        .map(PortfolioHolding.fromJson)
        .toList();

    return {
      'count': data['count'] ?? holdings.length,
      'total_invested': (data['total_invested'] as num?)?.toDouble() ?? 0,
      'holdings': holdings,
    };
  }

  Future<List<PortfolioSymbolSuggestion>> searchSymbols({
    required String query,
    required String searchType,
    int limit = 10,
  }) async {
    if (query.trim().length < 2) {
      return [];
    }

    final res = await ApiService.get(
      '${ApiConfig.apiUrl}/stocks/nse-global-search',
      queryParams: {
        'q': query.trim(),
        'type': searchType.toLowerCase(),
        'limit': '$limit',
      },
    );

    if (res.statusCode != 200) {
      return [];
    }

    final data = jsonDecode(res.body) as Map<String, dynamic>;
    final results = (data['results'] as List? ?? const []);
    return results
        .whereType<Map<String, dynamic>>()
        .map(PortfolioSymbolSuggestion.fromJson)
        .toList();
  }

  Future<int> getLotSize(String symbol) async {
    final res = await ApiService.get(ApiConfig.portfolioLotSize(symbol.toUpperCase()));
    if (res.statusCode != 200) {
      return 1;
    }
    final data = jsonDecode(res.body) as Map<String, dynamic>;
    return (data['lot_size'] as num?)?.toInt() ?? 1;
  }

  Future<DerivativeContractsData> getDerivativeContracts({
    required String symbol,
    required String instrumentType,
    String? expiry,
  }) async {
    final params = <String, String>{
      'instrument_type': instrumentType,
      if (expiry != null && expiry.isNotEmpty) 'expiry': expiry,
    };

    final res = await ApiService.get(
      ApiConfig.portfolioDerivativeContracts(symbol.toUpperCase()),
      queryParams: params,
    );

    if (res.statusCode != 200) {
      return DerivativeContractsData(expiries: const [], strikes: const [], selectedExpiry: null);
    }

    final data = jsonDecode(res.body) as Map<String, dynamic>;
    final expiries = (data['expiries'] as List? ?? const [])
        .map((e) => e.toString())
        .where((e) => e.isNotEmpty)
        .toList();
    final strikes = (data['strikes'] as List? ?? const [])
        .map((e) => (e as num?)?.toDouble())
        .whereType<double>()
        .toList()
      ..sort();

    return DerivativeContractsData(
      expiries: expiries,
      strikes: strikes,
      selectedExpiry: data['selected_expiry']?.toString(),
    );
  }

  Future<void> deleteHolding(int id) async {
    final res = await ApiService.delete('${ApiConfig.portfolioHoldings}/$id');
    if (res.statusCode != 200) {
      throw Exception('Unable to delete holding');
    }
  }

  Future<void> addHolding({
    required String symbol,
    required String instrumentType,
    int? qty,
    int? lots,
    required double avgPrice,
    String? expiry,
    double? strike,
    String? optionType,
    String? action,
    String? notes,
  }) async {
    final body = <String, dynamic>{
      'symbol': symbol.toUpperCase().trim(),
      'instrument_type': instrumentType,
      'avg_price': avgPrice,
      if (qty != null) 'qty': qty,
      if (lots != null) 'lots': lots,
      if (expiry != null && expiry.isNotEmpty) 'expiry': expiry,
      if (strike != null) 'strike': strike,
      if (optionType != null && optionType.isNotEmpty) 'option_type': optionType,
      if (action != null && action.isNotEmpty) 'action': action,
      if (notes != null && notes.isNotEmpty) 'notes': notes,
    };

    final res = await ApiService.post(ApiConfig.portfolioHoldings, body: body);
    if (res.statusCode != 200) {
      throw Exception('Unable to add holding');
    }
  }

  Future<void> updateHolding({
    required int id,
    int? qty,
    int? lots,
    double? avgPrice,
    String? expiry,
    double? strike,
    String? optionType,
    String? action,
    String? notes,
  }) async {
    final body = <String, dynamic>{
      if (qty != null) 'qty': qty,
      if (lots != null) 'lots': lots,
      if (avgPrice != null) 'avg_price': avgPrice,
      if (expiry != null && expiry.isNotEmpty) 'expiry': expiry,
      if (strike != null) 'strike': strike,
      if (optionType != null && optionType.isNotEmpty) 'option_type': optionType,
      if (action != null && action.isNotEmpty) 'action': action,
      if (notes != null) 'notes': notes,
    };

    final res = await ApiService.put('${ApiConfig.portfolioHoldings}/$id', body: body);
    if (res.statusCode != 200) {
      throw Exception('Unable to update holding');
    }
  }
}
