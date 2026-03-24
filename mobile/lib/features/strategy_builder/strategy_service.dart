import 'dart:convert';
import '../../core/services/api_service.dart';
import '../../config/api_config.dart';

class StrategyPosition {
  final String segment;
  final String expiry;
  final double? strike;
  final String? optionType;
  final String action;
  final int qty;
  final double entryPrice;

  StrategyPosition({
    required this.segment,
    required this.expiry,
    this.strike,
    this.optionType,
    required this.action,
    required this.qty,
    required this.entryPrice,
  });

  StrategyPosition copyWith({
    String? segment,
    String? expiry,
    double? strike,
    String? optionType,
    String? action,
    int? qty,
    double? entryPrice,
  }) {
    return StrategyPosition(
      segment: segment ?? this.segment,
      expiry: expiry ?? this.expiry,
      strike: strike ?? this.strike,
      optionType: optionType ?? this.optionType,
      action: action ?? this.action,
      qty: qty ?? this.qty,
      entryPrice: entryPrice ?? this.entryPrice,
    );
  }

  Map<String, dynamic> toJson() => {
    'segment': segment,
    'expiry': expiry,
    'strike': strike,
    'option_type': optionType,
    'action': action,
    'qty': qty,
    'entry_price': entryPrice,
  };

  factory StrategyPosition.fromJson(Map<String, dynamic> json) => StrategyPosition(
    segment: json['segment'],
    expiry: json['expiry'],
    strike: json['strike']?.toDouble(),
    optionType: json['option_type'],
    action: json['action'],
    qty: json['qty'],
    entryPrice: json['entry_price'].toDouble(),
  );
}

class StrategyModel {
  final int? id;
  final String name;
  final String symbol;
  final List<StrategyPosition> positions;
  final String? createdAt;

  StrategyModel({
    this.id,
    required this.name,
    required this.symbol,
    required this.positions,
    this.createdAt,
  });

  Map<String, dynamic> toJson() => {
    'name': name,
    'symbol': symbol,
    'positions': positions.map((p) => p.toJson()).toList(),
  };

  factory StrategyModel.fromJson(Map<String, dynamic> json) => StrategyModel(
    id: json['id'],
    name: json['name'],
    symbol: json['symbol'],
    positions: (json['positions'] as List).map((p) => StrategyPosition.fromJson(p)).toList(),
    createdAt: json['created_at'],
  );
}

class StrategyService {
  final String _strategyUrl = '${ApiConfig.apiUrl}/strategy';

  Future<List<String>> getSymbols() async {
    final res = await ApiService.get('$_strategyUrl/symbols');
    if (res.statusCode == 200) {
      final data = json.decode(res.body);
      return List<String>.from(data['symbols']);
    }
    return [];
  }

  Future<Map<String, dynamic>> getDropdowns(String symbol) async {
    final res = await ApiService.get('$_strategyUrl/dropdowns/${symbol.toUpperCase()}');
    return json.decode(res.body);
  }

  Future<Map<String, dynamic>> getSymbolData(String symbol) async {
    final res = await ApiService.get('$_strategyUrl/symbol-data/${symbol.toUpperCase()}');
    return json.decode(res.body);
  }

  Future<Map<String, dynamic>> getFuturesData(String symbol, {String? expiry, String? identifier}) async {
    final params = <String, String>{};
    if (expiry != null && expiry.isNotEmpty) params['expiry'] = expiry;
    if (identifier != null && identifier.isNotEmpty) params['identifier'] = identifier;
    final res = await ApiService.get(
      '$_strategyUrl/futures-data/${symbol.toUpperCase()}',
      queryParams: params.isNotEmpty ? params : null,
    );
    return json.decode(res.body);
  }

  Future<Map<String, dynamic>> getOptionChain(String symbol, {String? expiry}) async {
    final res = await ApiService.get(
      '$_strategyUrl/option-chain/${symbol.toUpperCase()}',
      queryParams: expiry != null ? {'expiry': expiry} : null,
    );
    return json.decode(res.body);
  }

  Future<bool> saveStrategy(StrategyModel strategy) async {
    final res = await ApiService.post(
      '$_strategyUrl/save',
      body: strategy.toJson(),
    );
    return res.statusCode == 200;
  }

  Future<Map<String, List<StrategyModel>>> getUserStrategies() async {
    final res = await ApiService.get('$_strategyUrl/user-strategies');
    if (res.statusCode == 200) {
      final data = json.decode(res.body);
      return {
        'live': (data['live'] as List).map((s) => StrategyModel.fromJson(s)).toList(),
        'history': (data['history'] as List).map((s) => StrategyModel.fromJson(s)).toList(),
      };
    }
    return {'live': [], 'history': []};
  }

  Future<bool> deleteStrategy(int id) async {
    final res = await ApiService.delete('$_strategyUrl/$id');
    return res.statusCode == 200;
  }
}
