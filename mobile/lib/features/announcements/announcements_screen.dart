import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:url_launcher/url_launcher.dart';
import '../../config/theme.dart';
import '../../core/models/announcement.dart';
import '../../core/services/announcement_service.dart';

class AnnouncementsScreen extends StatefulWidget {
  const AnnouncementsScreen({super.key});

  @override
  AnnouncementsScreenState createState() => AnnouncementsScreenState();
}

class AnnouncementsScreenState extends State<AnnouncementsScreen>
    with SingleTickerProviderStateMixin {
  void switchToBSE() {
    _tabController.animateTo(1);
  }

  late TabController _tabController;

  // NSE
  final _nseSymbolController = TextEditingController();
  List<NSEAnnouncement> _nseAnnouncements = [];
  bool _nseLoading = false;
  String? _nseError;
  DateTime _nseFromDate = DateTime.now().subtract(const Duration(days: 30));
  DateTime _nseToDate = DateTime.now();
  List<Map<String, String>> _nseSuggestions = [];
  bool _showNseSuggestions = false;
  String _selectedNseSymbol = '';
  String _selectedNseCompany = '';

  // BSE
  final _bseCompanyController = TextEditingController();
  DateTime _bseFromDate = DateTime.now();
  DateTime _bseToDate = DateTime.now();
  List<BSEAnnouncement> _bseAnnouncements = [];
  bool _bseLoading = false;
  String? _bseError;
  int _bsePage = 1;
  int _bseTotalPages = 0;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 2, vsync: this);
  }

  @override
  void dispose() {
    _tabController.dispose();
    _nseSymbolController.dispose();
    _bseCompanyController.dispose();
    super.dispose();
  }

  String _formatDate(DateTime date) => DateFormat('yyyy-MM-dd').format(date);

  Future<void> _pickNseDate(bool isFrom) async {
    final picked = await showDatePicker(
      context: context,
      initialDate: isFrom ? _nseFromDate : _nseToDate,
      firstDate: DateTime(2020),
      lastDate: DateTime.now(),
      builder: (context, child) {
        return Theme(
          data: AppTheme.darkTheme.copyWith(
            colorScheme: ColorScheme.dark(
              primary: AppTheme.primaryColor,
              surface: AppTheme.cardColor,
            ),
          ),
          child: child!,
        );
      },
    );
    if (picked != null) {
      setState(() {
        if (isFrom) {
          _nseFromDate = picked;
        } else {
          _nseToDate = picked;
        }
      });
    }
  }

  Future<void> _pickBseDate(bool isFrom) async {
    final picked = await showDatePicker(
      context: context,
      initialDate: isFrom ? _bseFromDate : _bseToDate,
      firstDate: DateTime(2020),
      lastDate: DateTime.now(),
      builder: (context, child) {
        return Theme(
          data: AppTheme.darkTheme.copyWith(
            colorScheme: ColorScheme.dark(
              primary: AppTheme.primaryColor,
              surface: AppTheme.cardColor,
            ),
          ),
          child: child!,
        );
      },
    );
    if (picked != null) {
      setState(() {
        if (isFrom) {
          _bseFromDate = picked;
        } else {
          _bseToDate = picked;
        }
      });
    }
  }

  Future<void> _fetchNseSuggestions(String query) async {
    if (query.length < 1) {
      setState(() {
        _nseSuggestions = [];
        _showNseSuggestions = false;
      });
      return;
    }
    try {
      final results = await AnnouncementService.nseAutocomplete(query);
      if (mounted) {
        setState(() {
          _nseSuggestions = results;
          _showNseSuggestions = results.isNotEmpty;
        });
      }
    } catch (_) {}
  }

  void _selectNseSuggestion(Map<String, String> suggestion) {
    FocusScope.of(context).unfocus();
    setState(() {
      _selectedNseSymbol = suggestion['symbol'] ?? '';
      _selectedNseCompany = suggestion['company_name'] ?? '';
      _nseSymbolController.text = _selectedNseSymbol;
      _nseSuggestions = [];
      _showNseSuggestions = false;
    });
  }

  Future<void> _loadNSEAnnouncements() async {
    final symbol = _selectedNseSymbol.isNotEmpty
        ? _selectedNseSymbol
        : _nseSymbolController.text.trim();
    if (symbol.isEmpty) return;

    setState(() {
      _nseLoading = true;
      _nseError = null;
    });
    try {
      final data = await AnnouncementService.getNSEAnnouncements(
        symbol.toUpperCase(),
        fromDate: _formatDate(_nseFromDate),
        toDate: _formatDate(_nseToDate),
      );
      setState(() {
        _nseAnnouncements = data;
        _nseLoading = false;
      });
    } catch (e) {
      setState(() {
        _nseError = e.toString().replaceAll('Exception: ', '');
        _nseLoading = false;
      });
    }
  }

  Future<void> _loadBSEAnnouncements({int page = 1}) async {
    setState(() {
      _bseLoading = true;
      _bseError = null;
    });
    try {
      final company = _bseCompanyController.text.trim();
      final result = await AnnouncementService.getBSEAnnouncements(
        fromDate: _formatDate(_bseFromDate),
        toDate: _formatDate(_bseToDate),
        scripCode: company.isNotEmpty ? company : null,
        page: page,
      );
      setState(() {
        _bseAnnouncements = result['announcements'];
        _bseTotalPages = result['total_pages'];
        _bsePage = page;
        _bseLoading = false;
      });
    } catch (e) {
      setState(() {
        _bseError = e.toString().replaceAll('Exception: ', '');
        _bseLoading = false;
      });
    }
  }

  Future<void> _openUrl(String? url) async {
    if (url == null || url.isEmpty) return;
    final uri = Uri.parse(url);
    if (await canLaunchUrl(uri)) {
      await launchUrl(uri, mode: LaunchMode.externalApplication);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Announcements'),
        bottom: TabBar(
          controller: _tabController,
          indicatorColor: AppTheme.primaryColor,
          labelColor: AppTheme.primaryColor,
          unselectedLabelColor: AppTheme.textSecondary,
          tabs: const [
            Tab(text: 'NSE'),
            Tab(text: 'BSE'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabController,
        children: [_buildNSETab(), _buildBSETab()],
      ),
    );
  }

  Widget _buildNSETab() {
    return GestureDetector(
      onTap: () {
        FocusScope.of(context).unfocus();
        setState(() => _showNseSuggestions = false);
      },
      child: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              children: [
                // Company search
                TextField(
                  controller: _nseSymbolController,
                  decoration: InputDecoration(
                    hintText: 'Search company / symbol',
                    prefixIcon: const Icon(Icons.search),
                    isDense: true,
                    suffixIcon: _nseSymbolController.text.isNotEmpty
                        ? IconButton(
                            icon: const Icon(Icons.clear, size: 18),
                            onPressed: () {
                              setState(() {
                                _nseSymbolController.clear();
                                _selectedNseSymbol = '';
                                _selectedNseCompany = '';
                                _showNseSuggestions = false;
                              });
                            },
                          )
                        : null,
                  ),
                  onChanged: (val) => _fetchNseSuggestions(val),
                  onSubmitted: (_) {
                    setState(() => _showNseSuggestions = false);
                    _loadNSEAnnouncements();
                  },
                ),
                // Suggestions dropdown (inline, not Positioned)
                if (_showNseSuggestions && _nseSuggestions.isNotEmpty)
                  Container(
                    margin: const EdgeInsets.only(top: 4),
                    constraints: const BoxConstraints(maxHeight: 200),
                    decoration: BoxDecoration(
                      color: AppTheme.cardColor,
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(
                        color: AppTheme.primaryColor.withValues(alpha: 0.3),
                      ),
                    ),
                    child: ListView.builder(
                      shrinkWrap: true,
                      padding: EdgeInsets.zero,
                      itemCount: _nseSuggestions.length,
                      itemBuilder: (context, index) {
                        final s = _nseSuggestions[index];
                        return InkWell(
                          onTap: () => _selectNseSuggestion(s),
                          child: Padding(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 16,
                              vertical: 10,
                            ),
                            child: Row(
                              children: [
                                Expanded(
                                  child: Column(
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    children: [
                                      Text(
                                        s['symbol'] ?? '',
                                        style: const TextStyle(
                                          fontWeight: FontWeight.w700,
                                          fontSize: 14,
                                        ),
                                      ),
                                      const SizedBox(height: 2),
                                      Text(
                                        s['company_name'] ?? '',
                                        style: TextStyle(
                                          fontSize: 12,
                                          color: AppTheme.textSecondary,
                                        ),
                                        maxLines: 1,
                                        overflow: TextOverflow.ellipsis,
                                      ),
                                    ],
                                  ),
                                ),
                                Icon(
                                  Icons.north_east,
                                  size: 14,
                                  color: AppTheme.textSecondary,
                                ),
                              ],
                            ),
                          ),
                        );
                      },
                    ),
                  ),
                const SizedBox(height: 12),
                // Date pickers row
                Row(
                  children: [
                    Expanded(
                      child: GestureDetector(
                        onTap: () => _pickNseDate(true),
                        child: InputDecorator(
                          decoration: const InputDecoration(
                            labelText: 'From',
                            isDense: true,
                            prefixIcon: Icon(Icons.calendar_today, size: 18),
                          ),
                          child: Text(
                            DateFormat('dd MMM yyyy').format(_nseFromDate),
                            style: const TextStyle(fontSize: 13),
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: GestureDetector(
                        onTap: () => _pickNseDate(false),
                        child: InputDecorator(
                          decoration: const InputDecoration(
                            labelText: 'To',
                            isDense: true,
                            prefixIcon: Icon(Icons.calendar_today, size: 18),
                          ),
                          child: Text(
                            DateFormat('dd MMM yyyy').format(_nseToDate),
                            style: const TextStyle(fontSize: 13),
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                // Search button
                SizedBox(
                  width: double.infinity,
                  child: ElevatedButton.icon(
                    onPressed: _nseLoading ? null : _loadNSEAnnouncements,
                    icon: _nseLoading
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              color: Colors.white,
                            ),
                          )
                        : const Icon(Icons.search, size: 18),
                    label: Text(
                      _nseLoading ? 'Searching...' : 'Search Announcements',
                    ),
                  ),
                ),
              ],
            ),
          ),

          if (_nseError != null) _buildErrorBanner(_nseError!),

          // Results
          Expanded(
            child: _nseAnnouncements.isEmpty
                ? Center(
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(
                          Icons.article_outlined,
                          size: 48,
                          color: AppTheme.textSecondary,
                        ),
                        const SizedBox(height: 12),
                        Text(
                          'Search a company and date range\nto view announcements',
                          textAlign: TextAlign.center,
                          style: TextStyle(color: AppTheme.textSecondary),
                        ),
                      ],
                    ),
                  )
                : RefreshIndicator(
                    onRefresh: _loadNSEAnnouncements,
                    child: ListView.builder(
                      padding: const EdgeInsets.all(16),
                      itemCount: _nseAnnouncements.length,
                      itemBuilder: (context, index) {
                        final ann = _nseAnnouncements[index];
                        return _buildAnnouncementCard(
                          company: ann.companyName,
                          subject: ann.subject,
                          date: ann.broadcastDate,
                          category: ann.category,
                          url: ann.attachmentLink.isNotEmpty
                              ? ann.attachmentLink
                              : null,
                        );
                      },
                    ),
                  ),
          ),
        ],
      ),
    );
  }

  Widget _buildBSETab() {
    return Column(
      children: [
        // Filters
        Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            children: [
              // Company name input
              TextField(
                controller: _bseCompanyController,
                decoration: const InputDecoration(
                  hintText: 'Company name or scrip code (optional)',
                  prefixIcon: Icon(Icons.business),
                  isDense: true,
                ),
                textCapitalization: TextCapitalization.characters,
                onSubmitted: (_) => _loadBSEAnnouncements(),
              ),
              const SizedBox(height: 12),

              // Date range
              Row(
                children: [
                  Expanded(
                    child: _buildBseDateCard(
                      'From',
                      _bseFromDate,
                      () => _pickBseDate(true),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: _buildBseDateCard(
                      'To',
                      _bseToDate,
                      () => _pickBseDate(false),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),

              // Search button
              SizedBox(
                width: double.infinity,
                child: ElevatedButton.icon(
                  onPressed: _bseLoading ? null : () => _loadBSEAnnouncements(),
                  icon: _bseLoading
                      ? const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            color: Colors.white,
                          ),
                        )
                      : const Icon(Icons.search),
                  label: Text(
                    _bseLoading ? 'Searching...' : 'Search BSE Announcements',
                  ),
                ),
              ),
            ],
          ),
        ),

        if (_bseError != null) _buildErrorBanner(_bseError!),

        // Results
        Expanded(
          child: _bseAnnouncements.isEmpty
              ? Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(
                        Icons.newspaper_outlined,
                        size: 48,
                        color: AppTheme.textSecondary,
                      ),
                      const SizedBox(height: 12),
                      Text(
                        'Set filters and search\nto view BSE announcements',
                        textAlign: TextAlign.center,
                        style: TextStyle(color: AppTheme.textSecondary),
                      ),
                    ],
                  ),
                )
              : ListView.builder(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  itemCount: _bseAnnouncements.length,
                  itemBuilder: (context, index) {
                    final ann = _bseAnnouncements[index];
                    return _buildAnnouncementCard(
                      company: ann.companyName,
                      subject: ann.subject,
                      date: ann.newsDate,
                      category: ann.category,
                      url: ann.attachmentUrl,
                    );
                  },
                ),
        ),

        // Pagination (matching stock comparison style)
        if (_bseTotalPages > 1) ...[
          const SizedBox(height: 8),
          Center(
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                IconButton(
                  onPressed: _bsePage > 1
                      ? () => _loadBSEAnnouncements(page: _bsePage - 1)
                      : null,
                  icon: const Icon(Icons.chevron_left),
                ),
                const SizedBox(width: 8),
                Text(
                  'Page $_bsePage of $_bseTotalPages',
                  style: TextStyle(
                    color: AppTheme.textSecondary,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(width: 8),
                IconButton(
                  onPressed: _bsePage < _bseTotalPages
                      ? () => _loadBSEAnnouncements(page: _bsePage + 1)
                      : null,
                  icon: const Icon(Icons.chevron_right),
                ),
              ],
            ),
          ),
          Center(
            child: Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Text(
                '${_bseAnnouncements.length} announcements loaded',
                style: TextStyle(fontSize: 12, color: AppTheme.textSecondary),
              ),
            ),
          ),
        ],
      ],
    );
  }

  Widget _buildBseDateCard(String label, DateTime date, VoidCallback onTap) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: AppTheme.cardColor,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: Colors.white12),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              label,
              style: TextStyle(fontSize: 12, color: AppTheme.textSecondary),
            ),
            const SizedBox(height: 4),
            Row(
              children: [
                const Icon(
                  Icons.calendar_today,
                  size: 14,
                  color: AppTheme.primaryColor,
                ),
                const SizedBox(width: 6),
                Text(
                  DateFormat('dd MMM yyyy').format(date),
                  style: const TextStyle(
                    fontWeight: FontWeight.w600,
                    fontSize: 13,
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildErrorBanner(String error) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: AppTheme.errorColor.withValues(alpha: 0.15),
          borderRadius: BorderRadius.circular(12),
        ),
        child: Row(
          children: [
            const Icon(
              Icons.error_outline,
              color: AppTheme.errorColor,
              size: 20,
            ),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                error,
                style: const TextStyle(color: AppTheme.errorColor),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildAnnouncementCard({
    required String company,
    required String subject,
    required String date,
    required String category,
    String? url,
  }) {
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppTheme.cardColor,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  company,
                  style: const TextStyle(
                    fontWeight: FontWeight.w700,
                    fontSize: 14,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              if (url != null)
                GestureDetector(
                  onTap: () => _openUrl(url),
                  child: Icon(
                    Icons.open_in_new,
                    size: 18,
                    color: AppTheme.accentColor,
                  ),
                ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            subject,
            style: const TextStyle(fontSize: 13),
            maxLines: 3,
            overflow: TextOverflow.ellipsis,
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              if (category.isNotEmpty)
                Flexible(
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 8,
                      vertical: 3,
                    ),
                    decoration: BoxDecoration(
                      color: AppTheme.primaryColor.withValues(alpha: 0.15),
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: Text(
                      category,
                      style: TextStyle(
                        fontSize: 10,
                        color: AppTheme.primaryColor,
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ),
              const SizedBox(width: 8),
              Text(
                date,
                style: TextStyle(fontSize: 11, color: AppTheme.textSecondary),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
