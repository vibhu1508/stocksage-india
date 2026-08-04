/// One strike of the option chain: the CE leg, the strike, the PE leg.
class OptionChainRow {
  final double strike;
  final double? ceLtp;
  final double? ceOi;
  final double? ceOiChange;
  final double? ceOiPctChange;
  final double? peLtp;
  final double? peOi;
  final double? peOiChange;
  final double? peOiPctChange;
  final double? pcr;

  OptionChainRow({
    required this.strike,
    this.ceLtp,
    this.ceOi,
    this.ceOiChange,
    this.ceOiPctChange,
    this.peLtp,
    this.peOi,
    this.peOiChange,
    this.peOiPctChange,
    this.pcr,
  });

  static double? _num(dynamic v) => v == null ? null : (v as num).toDouble();

  factory OptionChainRow.fromJson(Map<String, dynamic> json) {
    return OptionChainRow(
      strike: _num(json['StrkPric']) ?? 0,
      ceLtp: _num(json['CE_ClsPric']),
      ceOi: _num(json['CE_OpnIntrst']),
      ceOiChange: _num(json['CE_ChngInOpnIntrst']),
      ceOiPctChange: _num(json['CE_pct_oi_change']),
      peLtp: _num(json['PE_ClsPric']),
      peOi: _num(json['PE_OpnIntrst']),
      peOiChange: _num(json['PE_ChngInOpnIntrst']),
      peOiPctChange: _num(json['PE_pct_oi_change']),
      pcr: _num(json['PCR']),
    );
  }
}

/// Aggregate open-interest picture for one symbol/expiry.
class OptionChainSummary {
  final double totalCeOi;
  final double totalPeOi;
  final double? pcr;
  final double totalCeOiChange;
  final double totalPeOiChange;
  final double? maxCeOiStrike;
  final double? maxPeOiStrike;
  final double? atmStrike;

  OptionChainSummary({
    required this.totalCeOi,
    required this.totalPeOi,
    this.pcr,
    required this.totalCeOiChange,
    required this.totalPeOiChange,
    this.maxCeOiStrike,
    this.maxPeOiStrike,
    this.atmStrike,
  });

  static double? _num(dynamic v) => v == null ? null : (v as num).toDouble();

  factory OptionChainSummary.fromJson(Map<String, dynamic> json) {
    return OptionChainSummary(
      totalCeOi: _num(json['total_ce_oi']) ?? 0,
      totalPeOi: _num(json['total_pe_oi']) ?? 0,
      pcr: _num(json['pcr']),
      totalCeOiChange: _num(json['total_ce_oi_change']) ?? 0,
      totalPeOiChange: _num(json['total_pe_oi_change']) ?? 0,
      maxCeOiStrike: _num(json['max_ce_oi_strike']),
      maxPeOiStrike: _num(json['max_pe_oi_strike']),
      atmStrike: _num(json['atm_strike']),
    );
  }
}

/// Option chain for one symbol and expiry, plus the values that drive the filters.
class OptionChainData {
  final String date;
  final String symbol;
  final String? expiry;
  final List<String> availableSymbols;
  final List<String> availableExpiries;
  final double? underlyingPrice;
  final List<OptionChainRow> chain;
  final OptionChainSummary? summary;

  OptionChainData({
    required this.date,
    required this.symbol,
    this.expiry,
    required this.availableSymbols,
    required this.availableExpiries,
    this.underlyingPrice,
    required this.chain,
    this.summary,
  });

  factory OptionChainData.fromJson(Map<String, dynamic> json) {
    return OptionChainData(
      date: json['date'] ?? '',
      symbol: json['symbol'] ?? '',
      expiry: json['expiry'],
      availableSymbols: List<String>.from(json['available_symbols'] ?? []),
      availableExpiries: List<String>.from(json['available_expiries'] ?? []),
      underlyingPrice: (json['underlying_price'] as num?)?.toDouble(),
      chain: (json['chain'] as List? ?? [])
          .map((e) => OptionChainRow.fromJson(Map<String, dynamic>.from(e)))
          .toList(),
      summary: json['summary'] == null
          ? null
          : OptionChainSummary.fromJson(
              Map<String, dynamic>.from(json['summary']),
            ),
    );
  }
}

/// NIFTY tab payload: the index option chain plus its futures contracts.
class NiftyData extends OptionChainData {
  final int futuresCount;
  final int optionsCount;
  final List<Map<String, dynamic>> futures;
  final List<Map<String, dynamic>> options;

  NiftyData({
    required super.date,
    required super.symbol,
    super.expiry,
    required super.availableSymbols,
    required super.availableExpiries,
    super.underlyingPrice,
    required super.chain,
    super.summary,
    required this.futuresCount,
    required this.optionsCount,
    required this.futures,
    required this.options,
  });

  factory NiftyData.fromJson(Map<String, dynamic> json) {
    final base = OptionChainData.fromJson(json);
    return NiftyData(
      date: base.date,
      symbol: base.symbol,
      expiry: base.expiry,
      availableSymbols: base.availableSymbols,
      availableExpiries: base.availableExpiries,
      underlyingPrice: base.underlyingPrice,
      chain: base.chain,
      summary: base.summary,
      futuresCount: json['futures_count'] ?? 0,
      optionsCount: json['options_count'] ?? 0,
      futures: List<Map<String, dynamic>>.from(json['futures'] ?? []),
      options: List<Map<String, dynamic>>.from(json['options'] ?? []),
    );
  }
}

/// Futures tab payload: contracts for one segment, plus its filter values.
class FuturesTableData {
  final String date;
  final String segment;
  final String? expiry;
  final String? symbol;
  final List<String> availableExpiries;
  final List<String> availableSymbols;
  final List<Map<String, dynamic>> rows;

  FuturesTableData({
    required this.date,
    required this.segment,
    this.expiry,
    this.symbol,
    required this.availableExpiries,
    required this.availableSymbols,
    required this.rows,
  });

  factory FuturesTableData.fromJson(Map<String, dynamic> json) {
    return FuturesTableData(
      date: json['date'] ?? '',
      segment: json['segment'] ?? 'index',
      expiry: json['expiry'],
      symbol: json['symbol'],
      availableExpiries: List<String>.from(json['available_expiries'] ?? []),
      availableSymbols: List<String>.from(json['available_symbols'] ?? []),
      rows: List<Map<String, dynamic>>.from(json['rows'] ?? []),
    );
  }
}

class FOData {
  final String date;
  final int count;
  final List<Map<String, dynamic>> data;

  FOData({required this.date, required this.count, required this.data});

  factory FOData.fromJson(Map<String, dynamic> json) {
    return FOData(
      date: json['date'] ?? json['symbol'] ?? '',
      count: json['count'] ?? 0,
      data: List<Map<String, dynamic>>.from(json['data'] ?? []),
    );
  }
}
