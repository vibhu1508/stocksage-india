import 'package:flutter/material.dart';

import '../../core/services/auth_service.dart';
import '../../shared/widgets/profile_menu.dart';
import '../profile/profile_screen.dart';
import '../strategy_builder/strategy_builder_screen.dart';
import '../strategy_builder/strategy_service.dart';
import 'portfolio_service.dart';

class PortfolioScreen extends StatefulWidget {
  final AuthService authService;

  const PortfolioScreen({super.key, required this.authService});

  @override
  State<PortfolioScreen> createState() => _PortfolioScreenState();
}

class _PortfolioScreenState extends State<PortfolioScreen> {
  final PortfolioService _service = PortfolioService();

  bool _loading = true;
  String? _error;
  int _count = 0;
  double _totalInvested = 0;
  List<PortfolioHolding> _holdings = [];

  @override
  void initState() {
    super.initState();
    _loadHoldings();
  }

  Future<void> _loadHoldings({bool showSyncedToast = false}) async {
    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      final result = await _service.getHoldings();
      setState(() {
        _count = result['count'] as int;
        _totalInvested = result['total_invested'] as double;
        _holdings = (result['holdings'] as List<PortfolioHolding>);
      });
    } catch (e) {
      setState(() {
        _error = e.toString().replaceAll('Exception: ', '');
      });
    } finally {
      if (mounted) {
        setState(() => _loading = false);
        if (showSyncedToast) {
          _showToast('Portfolio synced');
        }
      }
    }
  }

  void _showToast(String message, {bool isError = false}) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).hideCurrentSnackBar();
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        behavior: SnackBarBehavior.floating,
        backgroundColor: isError ? Theme.of(context).colorScheme.error : null,
      ),
    );
  }

  Future<void> _confirmDelete(PortfolioHolding holding) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete Holding'),
        content: Text('Remove ${holding.symbol} from portfolio?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            style: FilledButton.styleFrom(backgroundColor: Theme.of(ctx).colorScheme.error),
            child: const Text('Delete'),
          ),
        ],
      ),
    );

    if (ok != true) return;

    try {
      await _service.deleteHolding(holding.id);
      await _loadHoldings();
      _showToast('Holding deleted');
    } catch (e) {
      _showToast(e.toString().replaceAll('Exception: ', ''), isError: true);
    }
  }

  Future<void> _openHoldingSheet({PortfolioHolding? existing}) async {
    final symbolCtrl = TextEditingController(text: existing?.symbol ?? '');
    final symbolFocusNode = FocusNode();
    final avgPriceCtrl = TextEditingController(
      text: existing != null ? existing.avgPrice.toStringAsFixed(2) : '',
    );
    final qtyOrLotsCtrl = TextEditingController(
      text: existing == null
          ? ''
          : (existing.instrumentType == 'EQUITY' ? existing.qty.toString() : (existing.lots > 0 ? existing.lots.toString() : existing.qty.toString())),
    );
    final expiryCtrl = TextEditingController(text: existing?.expiry ?? '');
    final strikeCtrl = TextEditingController(
      text: existing?.strike != null ? existing!.strike!.toStringAsFixed(0) : '',
    );
    final notesCtrl = TextEditingController(text: existing?.notes ?? '');

    String instrumentType = existing?.instrumentType ?? 'EQUITY';
    String optionType = existing?.optionType ?? 'CE';
    String action = existing?.action ?? 'BUY';
    String symbolSearchType = instrumentType == 'EQUITY' ? 'equity' : 'derivatives';
    bool submitting = false;

    bool searchingSymbols = false;
    bool suppressSymbolSearch = false;
    String symbolError = '';
    String avgPriceError = '';
    String qtyOrLotsError = '';
    String expiryError = '';
    String strikeError = '';
    String? lotHint;
    int symbolSearchRequestId = 0;
    int contractRequestId = 0;

    List<PortfolioSymbolSuggestion> symbolSuggestions = const [];
    PortfolioSymbolSuggestion? selectedSuggestion;
    List<String> availableExpiries = const [];
    List<double> availableStrikes = const [];
    bool loadingContracts = false;

    List<String> allowedInstrumentTypes() {
      const all = ['EQUITY', 'FUTURE', 'OPTION'];
      var allowed = selectedSuggestion?.allowedInstruments ?? all;
      if (allowed.isEmpty) {
        allowed = all;
      }

      if (symbolSearchType == 'derivatives') {
        allowed = allowed.where((e) => e == 'FUTURE' || e == 'OPTION').toList();
      } else {
        allowed = allowed.where((e) => e == 'EQUITY').toList();
      }

      if (allowed.isEmpty) {
        return symbolSearchType == 'derivatives' ? ['FUTURE', 'OPTION'] : ['EQUITY'];
      }
      return allowed;
    }

    Future<void> runSymbolSearch(
      void Function(void Function()) setModalState,
      String rawQuery,
    ) async {
      final query = rawQuery.trim();
      if (query.length < 2 || existing != null || suppressSymbolSearch) {
        setModalState(() {
          symbolSuggestions = const [];
          searchingSymbols = false;
        });
        return;
      }

      final currentRequest = ++symbolSearchRequestId;
      setModalState(() {
        searchingSymbols = true;
      });

      try {
        final results = await _service.searchSymbols(
          query: query,
          searchType: symbolSearchType,
          limit: 8,
        );
        if (!mounted || currentRequest != symbolSearchRequestId) return;
        setModalState(() {
          symbolSuggestions = results;
          selectedSuggestion = null;
          searchingSymbols = false;
        });
      } catch (_) {
        if (!mounted || currentRequest != symbolSearchRequestId) return;
        setModalState(() {
          symbolSuggestions = const [];
          searchingSymbols = false;
        });
      }
    }

    Future<void> loadContracts(void Function(void Function()) setModalState) async {
      if (instrumentType == 'EQUITY') {
        setModalState(() {
          availableExpiries = const [];
          availableStrikes = const [];
          loadingContracts = false;
          expiryError = '';
          strikeError = '';
        });
        return;
      }

      final symbol = symbolCtrl.text.trim().toUpperCase();
      if (symbol.length < 2) {
        setModalState(() {
          availableExpiries = const [];
          availableStrikes = const [];
          loadingContracts = false;
        });
        return;
      }

      final currentRequest = ++contractRequestId;
      setModalState(() {
        loadingContracts = true;
      });

      try {
        final contracts = await _service.getDerivativeContracts(
          symbol: symbol,
          instrumentType: instrumentType,
          expiry: expiryCtrl.text.trim().isEmpty ? null : expiryCtrl.text.trim(),
        );
        if (!mounted || currentRequest != contractRequestId) return;

        if (expiryCtrl.text.trim().isEmpty && contracts.selectedExpiry != null) {
          expiryCtrl.text = contracts.selectedExpiry!;
        }

        setModalState(() {
          availableExpiries = contracts.expiries;
          availableStrikes = contracts.strikes;
          loadingContracts = false;
        });
      } catch (_) {
        if (!mounted || currentRequest != contractRequestId) return;
        setModalState(() {
          availableExpiries = const [];
          availableStrikes = const [];
          loadingContracts = false;
        });
      }
    }

    Future<void> loadLotHint(void Function(void Function()) setModalState) async {
      if (instrumentType == 'EQUITY') {
        setModalState(() => lotHint = null);
        return;
      }

      final symbol = symbolCtrl.text.trim().toUpperCase();
      if (symbol.length < 2) {
        setModalState(() => lotHint = null);
        return;
      }

      try {
        final lotSize = await _service.getLotSize(symbol);
        if (!mounted) return;
        setModalState(() => lotHint = lotSize > 1 ? '1 lot = $lotSize qty' : null);
      } catch (_) {
        if (!mounted) return;
        setModalState(() => lotHint = null);
      }
    }

    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (ctx) {
        return StatefulBuilder(
          builder: (context, setModalState) {
            final isDerivative = instrumentType != 'EQUITY';

            Future<void> submit() async {
              final symbol = symbolCtrl.text.trim().toUpperCase();
              final avgPrice = double.tryParse(avgPriceCtrl.text.trim());
              final qtyOrLots = int.tryParse(qtyOrLotsCtrl.text.trim());
              final strike = double.tryParse(strikeCtrl.text.trim());

              setModalState(() {
                symbolError = '';
                avgPriceError = '';
                qtyOrLotsError = '';
                expiryError = '';
                strikeError = '';
              });

              if (symbol.isEmpty) {
                setModalState(() => symbolError = 'Symbol is required');
                return;
              }
              if (avgPrice == null || avgPrice <= 0) {
                setModalState(() => avgPriceError = 'Average price must be positive');
                return;
              }
              if (qtyOrLots == null || qtyOrLots <= 0) {
                setModalState(() {
                  qtyOrLotsError = isDerivative ? 'Lots must be positive' : 'Quantity must be positive';
                });
                return;
              }
              if (instrumentType == 'OPTION' && expiryCtrl.text.trim().isEmpty) {
                setModalState(() => expiryError = 'Expiry is required for option positions');
                return;
              }
              if (instrumentType == 'OPTION' && (strike == null || strike <= 0)) {
                setModalState(() => strikeError = 'Strike must be positive for option positions');
                return;
              }

              setModalState(() => submitting = true);
              try {
                if (existing == null) {
                  await _service.addHolding(
                    symbol: symbol,
                    instrumentType: instrumentType,
                    qty: isDerivative ? null : qtyOrLots,
                    lots: isDerivative ? qtyOrLots : null,
                    avgPrice: avgPrice,
                    expiry: expiryCtrl.text.trim().isEmpty ? null : expiryCtrl.text.trim(),
                    strike: strike,
                    optionType: instrumentType == 'OPTION' ? optionType : null,
                    action: isDerivative ? action : null,
                    notes: notesCtrl.text.trim().isEmpty ? null : notesCtrl.text.trim(),
                  );
                  _showToast('Holding added');
                } else {
                  await _service.updateHolding(
                    id: existing.id,
                    qty: isDerivative ? null : qtyOrLots,
                    lots: isDerivative ? qtyOrLots : null,
                    avgPrice: avgPrice,
                    expiry: expiryCtrl.text.trim().isEmpty ? null : expiryCtrl.text.trim(),
                    strike: strike,
                    optionType: instrumentType == 'OPTION' ? optionType : null,
                    action: isDerivative ? action : null,
                    notes: notesCtrl.text.trim(),
                  );
                  _showToast('Holding updated');
                }

                if (ctx.mounted) {
                  Navigator.pop(ctx);
                }
                await _loadHoldings();
              } catch (e) {
                _showToast(e.toString().replaceAll('Exception: ', ''), isError: true);
              } finally {
                if (ctx.mounted) {
                  setModalState(() => submitting = false);
                }
              }
            }

            return Padding(
              padding: EdgeInsets.only(
                left: 16,
                right: 16,
                top: 16,
                bottom: MediaQuery.of(ctx).viewInsets.bottom + 16,
              ),
              child: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(existing == null ? 'Add Holding' : 'Edit Holding', style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
                    const SizedBox(height: 12),
                    if (existing == null) ...[
                      Wrap(
                        spacing: 8,
                        runSpacing: 8,
                        children: [
                          ChoiceChip(
                            label: const Text('Equity'),
                            selected: symbolSearchType == 'equity',
                            onSelected: (_) {
                              setModalState(() {
                                symbolSearchType = 'equity';
                                instrumentType = 'EQUITY';
                                selectedSuggestion = null;
                                availableExpiries = const [];
                                availableStrikes = const [];
                                expiryCtrl.clear();
                                strikeCtrl.clear();
                                lotHint = null;
                              });
                              runSymbolSearch(setModalState, symbolCtrl.text);
                            },
                          ),
                          ChoiceChip(
                            label: const Text('Derivatives'),
                            selected: symbolSearchType == 'derivatives',
                            onSelected: (_) {
                              setModalState(() {
                                symbolSearchType = 'derivatives';
                                selectedSuggestion = null;
                                if (instrumentType == 'EQUITY') {
                                  instrumentType = 'FUTURE';
                                }
                              });
                              runSymbolSearch(setModalState, symbolCtrl.text);
                              loadLotHint(setModalState);
                              loadContracts(setModalState);
                            },
                          ),
                          ChoiceChip(
                            label: const Text('ETF'),
                            selected: symbolSearchType == 'etf',
                            onSelected: (_) {
                              setModalState(() {
                                symbolSearchType = 'etf';
                                instrumentType = 'EQUITY';
                                selectedSuggestion = null;
                                availableExpiries = const [];
                                availableStrikes = const [];
                                expiryCtrl.clear();
                                strikeCtrl.clear();
                                lotHint = null;
                              });
                              runSymbolSearch(setModalState, symbolCtrl.text);
                            },
                          ),
                        ],
                      ),
                      const SizedBox(height: 10),
                    ],
                    TextField(
                      controller: symbolCtrl,
                      focusNode: symbolFocusNode,
                      enabled: existing == null,
                      onChanged: existing == null
                          ? (value) async {
                              if (suppressSymbolSearch) return;
                              await runSymbolSearch(setModalState, value);
                            }
                          : null,
                      decoration: InputDecoration(
                        labelText: 'Symbol',
                        border: const OutlineInputBorder(),
                        errorText: symbolError.isEmpty ? null : symbolError,
                        suffixIcon: searchingSymbols
                            ? const Padding(
                                padding: EdgeInsets.all(10),
                                child: SizedBox(
                                  width: 18,
                                  height: 18,
                                  child: CircularProgressIndicator(strokeWidth: 2),
                                ),
                              )
                            : null,
                      ),
                    ),
                    if (existing == null && symbolSuggestions.isNotEmpty && symbolFocusNode.hasFocus) ...[
                      const SizedBox(height: 6),
                      ConstrainedBox(
                        constraints: const BoxConstraints(maxHeight: 180),
                        child: Container(
                          decoration: BoxDecoration(
                            borderRadius: BorderRadius.circular(10),
                            border: Border.all(color: Colors.white12),
                            color: Theme.of(context).cardColor,
                          ),
                          child: ListView.separated(
                            itemCount: symbolSuggestions.length,
                            separatorBuilder: (_, __) => const Divider(height: 1),
                            itemBuilder: (context, index) {
                              final s = symbolSuggestions[index];
                              return ListTile(
                                dense: true,
                                title: Text(s.symbol),
                                subtitle: Text(
                                  s.name.isEmpty ? s.series : '${s.name} (${s.series})',
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                ),
                                onTap: () async {
                                  final allowed = s.allowedInstruments;
                                  final nextInstrument = (() {
                                    if (symbolSearchType == 'derivatives') {
                                      if (allowed.contains('FUTURE')) return 'FUTURE';
                                      if (allowed.contains('OPTION')) return 'OPTION';
                                      return 'FUTURE';
                                    }
                                    return 'EQUITY';
                                  })();

                                  suppressSymbolSearch = true;
                                  symbolCtrl.text = s.symbol;
                                  symbolCtrl.selection = TextSelection.collapsed(offset: symbolCtrl.text.length);
                                  setModalState(() {
                                    selectedSuggestion = s;
                                    instrumentType = nextInstrument;
                                    symbolSuggestions = const [];
                                    searchingSymbols = false;
                                    symbolError = '';
                                  });
                                  symbolFocusNode.unfocus();
                                  Future.delayed(const Duration(milliseconds: 120), () {
                                    suppressSymbolSearch = false;
                                  });
                                  await loadLotHint(setModalState);
                                  await loadContracts(setModalState);
                                },
                              );
                            },
                          ),
                        ),
                      ),
                    ],
                    const SizedBox(height: 10),
                    DropdownButtonFormField<String>(
                      initialValue: instrumentType,
                      items: allowedInstrumentTypes()
                          .map((e) => DropdownMenuItem<String>(value: e, child: Text(e)))
                          .toList(),
                      onChanged: existing == null
                          ? (value) {
                              if (value != null) {
                                setModalState(() {
                                  instrumentType = value;
                                  symbolSearchType = instrumentType == 'EQUITY' ? 'equity' : 'derivatives';
                                  if (instrumentType == 'EQUITY') {
                                    expiryCtrl.clear();
                                    strikeCtrl.clear();
                                    availableExpiries = const [];
                                    availableStrikes = const [];
                                    lotHint = null;
                                  }
                                  if (instrumentType == 'FUTURE') {
                                    strikeCtrl.clear();
                                  }
                                });
                                runSymbolSearch(setModalState, symbolCtrl.text);
                                loadLotHint(setModalState);
                                loadContracts(setModalState);
                              }
                            }
                          : null,
                      decoration: const InputDecoration(labelText: 'Instrument Type', border: OutlineInputBorder()),
                    ),
                    const SizedBox(height: 10),
                    TextField(
                      controller: qtyOrLotsCtrl,
                      keyboardType: TextInputType.number,
                      decoration: InputDecoration(
                        labelText: isDerivative ? 'Lots' : 'Quantity',
                        border: const OutlineInputBorder(),
                        helperText: isDerivative ? lotHint : null,
                        errorText: qtyOrLotsError.isEmpty ? null : qtyOrLotsError,
                      ),
                    ),
                    const SizedBox(height: 10),
                    TextField(
                      controller: avgPriceCtrl,
                      keyboardType: const TextInputType.numberWithOptions(decimal: true),
                      decoration: InputDecoration(
                        labelText: 'Average Price',
                        border: const OutlineInputBorder(),
                        errorText: avgPriceError.isEmpty ? null : avgPriceError,
                      ),
                    ),
                    if (isDerivative) ...[
                      if (loadingContracts)
                        const Padding(
                          padding: EdgeInsets.only(bottom: 10),
                          child: LinearProgressIndicator(minHeight: 2),
                        ),
                      const SizedBox(height: 10),
                      if (availableExpiries.isNotEmpty)
                        DropdownButtonFormField<String>(
                          initialValue: availableExpiries.contains(expiryCtrl.text.trim()) ? expiryCtrl.text.trim() : null,
                          items: availableExpiries
                              .map((e) => DropdownMenuItem<String>(value: e, child: Text(e)))
                              .toList(),
                          onChanged: (value) async {
                            if (value == null) return;
                            expiryCtrl.text = value;
                            setModalState(() {
                              expiryError = '';
                            });
                            await loadContracts(setModalState);
                          },
                          decoration: InputDecoration(
                            labelText: 'Expiry',
                            border: const OutlineInputBorder(),
                            errorText: expiryError.isEmpty ? null : expiryError,
                          ),
                        )
                      else
                        TextField(
                          controller: expiryCtrl,
                          onChanged: (_) {
                            setModalState(() => expiryError = '');
                          },
                          decoration: InputDecoration(
                            labelText: 'Expiry',
                            border: const OutlineInputBorder(),
                            errorText: expiryError.isEmpty ? null : expiryError,
                          ),
                        ),
                      const SizedBox(height: 10),
                      if (instrumentType == 'OPTION')
                        (availableStrikes.isNotEmpty
                            ? DropdownButtonFormField<double>(
                            initialValue: availableStrikes.contains(double.tryParse(strikeCtrl.text.trim()))
                                    ? double.tryParse(strikeCtrl.text.trim())
                                    : null,
                                items: availableStrikes
                                    .map(
                                      (s) => DropdownMenuItem<double>(
                                        value: s,
                                        child: Text(s.toStringAsFixed(0)),
                                      ),
                                    )
                                    .toList(),
                                onChanged: (value) {
                                  if (value == null) return;
                                  strikeCtrl.text = value.toStringAsFixed(0);
                                  setModalState(() => strikeError = '');
                                },
                                decoration: InputDecoration(
                                  labelText: 'Strike',
                                  border: const OutlineInputBorder(),
                                  errorText: strikeError.isEmpty ? null : strikeError,
                                ),
                              )
                            : TextField(
                                controller: strikeCtrl,
                                onChanged: (_) {
                                  setModalState(() => strikeError = '');
                                },
                                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                                decoration: InputDecoration(
                                  labelText: 'Strike',
                                  border: const OutlineInputBorder(),
                                  errorText: strikeError.isEmpty ? null : strikeError,
                                ),
                              )),
                      const SizedBox(height: 10),
                      if (instrumentType == 'OPTION')
                        DropdownButtonFormField<String>(
                          initialValue: optionType,
                          items: const [
                            DropdownMenuItem(value: 'CE', child: Text('CE')),
                            DropdownMenuItem(value: 'PE', child: Text('PE')),
                          ],
                          onChanged: (value) {
                            if (value != null) {
                              setModalState(() => optionType = value);
                            }
                          },
                          decoration: const InputDecoration(labelText: 'Option Type', border: OutlineInputBorder()),
                        ),
                      const SizedBox(height: 10),
                      DropdownButtonFormField<String>(
                        initialValue: action,
                        items: const [
                          DropdownMenuItem(value: 'BUY', child: Text('BUY')),
                          DropdownMenuItem(value: 'SELL', child: Text('SELL')),
                        ],
                        onChanged: (value) {
                          if (value != null) {
                            setModalState(() => action = value);
                          }
                        },
                        decoration: const InputDecoration(labelText: 'Action', border: OutlineInputBorder()),
                      ),
                    ],
                    const SizedBox(height: 10),
                    TextField(
                      controller: notesCtrl,
                      maxLines: 2,
                      decoration: const InputDecoration(labelText: 'Notes (optional)', border: OutlineInputBorder()),
                    ),
                    const SizedBox(height: 14),
                    SizedBox(
                      width: double.infinity,
                      child: FilledButton(
                        onPressed: submitting ? null : submit,
                        child: Text(submitting ? 'Saving...' : (existing == null ? 'Add Holding' : 'Save Changes')),
                      ),
                    ),
                  ],
                ),
              ),
            );
          },
        );
      },
    );

    symbolFocusNode.dispose();
  }

  void _openHoldingInStrategyBuilder(PortfolioHolding h) {
    if (h.instrumentType != 'OPTION') {
      _showToast('Only option holdings can be sent to Strategy Builder', isError: true);
      return;
    }
    if (h.strike == null || h.optionType == null || h.expiry == null || h.expiry!.isEmpty) {
      _showToast('Complete expiry/strike/option details before adding to builder', isError: true);
      return;
    }

    final position = StrategyPosition(
      segment: 'OPTIDX',
      expiry: h.expiry!,
      strike: h.strike,
      optionType: h.optionType,
      action: (h.action ?? 'BUY').toUpperCase() == 'SELL' ? 'SELL' : 'BUY',
      qty: h.lots > 0 ? h.lots : 1,
      entryPrice: h.avgPrice,
    );

    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => StrategyBuilderScreen(
          initialSymbol: h.symbol,
          initialPositions: [position],
        ),
      ),
    );
  }

  String _formatHoldingMeta(PortfolioHolding h) {
    if (h.instrumentType == 'EQUITY') {
      return 'Qty ${h.qty}';
    }

    final parts = <String>[];
    if (h.lots > 0) {
      parts.add('${h.lots} lots');
    }
    if (h.expiry != null && h.expiry!.isNotEmpty) {
      parts.add(h.expiry!);
    }
    if (h.strike != null) {
      parts.add(h.strike!.toStringAsFixed(0));
    }
    if (h.optionType != null) {
      parts.add(h.optionType!);
    }
    if (h.action != null) {
      parts.add(h.action!);
    }

    return parts.join(' • ');
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Portfolio'),
        actions: [
          ProfileMenu(
            authService: widget.authService,
            onOpenProfile: () {
              Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (_) => ProfileScreen(authService: widget.authService),
                ),
              );
            },
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () => _loadHoldings(showSyncedToast: true),
        child: _loading
            ? const Center(child: CircularProgressIndicator())
            : _error != null
                ? ListView(
                    children: [
                      const SizedBox(height: 120),
                      Center(
                        child: Padding(
                          padding: const EdgeInsets.all(16),
                          child: Text(
                            _error!,
                            textAlign: TextAlign.center,
                            style: TextStyle(color: theme.colorScheme.error),
                          ),
                        ),
                      ),
                    ],
                  )
                : ListView(
                    padding: const EdgeInsets.fromLTRB(16, 12, 16, 20),
                    children: [
                      Container(
                        padding: const EdgeInsets.all(16),
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(16),
                          border: Border.all(color: Colors.white10),
                          color: theme.cardColor,
                        ),
                        child: Row(
                          children: [
                            Expanded(
                              child: _MetricTile(
                                label: 'Total Holdings',
                                value: '$_count',
                              ),
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              child: _MetricTile(
                                label: 'Total Invested',
                                value: 'Rs ${_totalInvested.toStringAsFixed(2)}',
                              ),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 14),
                      if (_holdings.isEmpty)
                        Container(
                          padding: const EdgeInsets.all(20),
                          decoration: BoxDecoration(
                            borderRadius: BorderRadius.circular(16),
                            border: Border.all(color: Colors.white10),
                            color: theme.cardColor,
                          ),
                          child: const Text(
                            'No holdings yet. Add portfolio positions on web or app and they will sync for this account.',
                            textAlign: TextAlign.center,
                          ),
                        )
                      else
                        ..._holdings.map(
                          (h) => Container(
                            margin: const EdgeInsets.only(bottom: 10),
                            padding: const EdgeInsets.all(14),
                            decoration: BoxDecoration(
                              borderRadius: BorderRadius.circular(14),
                              border: Border.all(color: Colors.white10),
                              color: theme.cardColor,
                            ),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Row(
                                  children: [
                                    Expanded(
                                      child: Text(
                                        h.symbol,
                                        style: const TextStyle(
                                          fontSize: 16,
                                          fontWeight: FontWeight.w700,
                                        ),
                                      ),
                                    ),
                                    Container(
                                      padding: const EdgeInsets.symmetric(
                                        horizontal: 8,
                                        vertical: 4,
                                      ),
                                      decoration: BoxDecoration(
                                        borderRadius: BorderRadius.circular(999),
                                        color: Colors.blue.withValues(alpha: 0.15),
                                      ),
                                      child: Text(
                                        h.instrumentType,
                                        style: const TextStyle(fontSize: 11),
                                      ),
                                    ),
                                  ],
                                ),
                                const SizedBox(height: 6),
                                Text(
                                  _formatHoldingMeta(h),
                                  style: TextStyle(
                                    fontSize: 12,
                                    color: theme.textTheme.bodySmall?.color?.withOpacity(0.75),
                                  ),
                                ),
                                const SizedBox(height: 8),
                                Text(
                                  'Avg Rs ${h.avgPrice.toStringAsFixed(2)} • Invested Rs ${h.invested.toStringAsFixed(2)}',
                                  style: TextStyle(
                                    fontSize: 13,
                                    color: theme.textTheme.bodyMedium?.color?.withOpacity(0.85),
                                  ),
                                ),
                                const SizedBox(height: 10),
                                Wrap(
                                  spacing: 8,
                                  runSpacing: 8,
                                  children: [
                                    OutlinedButton.icon(
                                      onPressed: () => _openHoldingSheet(existing: h),
                                      icon: const Icon(Icons.edit_outlined, size: 16),
                                      label: const Text('Edit'),
                                    ),
                                    OutlinedButton.icon(
                                      onPressed: () => _confirmDelete(h),
                                      icon: const Icon(Icons.delete_outline, size: 16),
                                      label: const Text('Delete'),
                                    ),
                                    if (h.instrumentType == 'OPTION')
                                      FilledButton.tonalIcon(
                                        onPressed: () => _openHoldingInStrategyBuilder(h),
                                        icon: const Icon(Icons.hub_outlined, size: 16),
                                        label: const Text('Open in Builder'),
                                      ),
                                  ],
                                ),
                              ],
                            ),
                          ),
                        ),
                    ],
                  ),
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _openHoldingSheet(),
        icon: const Icon(Icons.add),
        label: const Text('Add Holding'),
      ),
    );
  }
}

class _MetricTile extends StatelessWidget {
  final String label;
  final String value;

  const _MetricTile({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: TextStyle(
            fontSize: 12,
            color: Theme.of(context).textTheme.bodySmall?.color?.withOpacity(0.75),
          ),
        ),
        const SizedBox(height: 4),
        Text(
          value,
          style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
        ),
      ],
    );
  }
}
