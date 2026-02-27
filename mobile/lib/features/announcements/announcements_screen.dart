import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:url_launcher/url_launcher.dart';
import '../../config/theme.dart';
import '../../core/models/announcement.dart';
import '../../core/services/announcement_service.dart';

class AnnouncementsScreen extends StatefulWidget {
  const AnnouncementsScreen({super.key});

  @override
  State<AnnouncementsScreen> createState() => _AnnouncementsScreenState();
}

class _AnnouncementsScreenState extends State<AnnouncementsScreen>
    with SingleTickerProviderStateMixin {
  late TabController _tabController;

  // NSE
  final _nseSymbolController = TextEditingController(text: 'RELIANCE');
  List<NSEAnnouncement> _nseAnnouncements = [];
  bool _nseLoading = false;
  String? _nseError;

  // BSE
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
    super.dispose();
  }

  Future<void> _loadNSEAnnouncements() async {
    final symbol = _nseSymbolController.text.trim();
    if (symbol.isEmpty) return;

    setState(() {
      _nseLoading = true;
      _nseError = null;
    });
    try {
      final data = await AnnouncementService.getNSEAnnouncements(
        symbol.toUpperCase(),
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
      final today = DateFormat('yyyy-MM-dd').format(DateTime.now());
      final result = await AnnouncementService.getBSEAnnouncements(
        fromDate: today,
        toDate: today,
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
    return Column(
      children: [
        // Search bar
        Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _nseSymbolController,
                  decoration: const InputDecoration(
                    hintText: 'Enter symbol (e.g., RELIANCE)',
                    prefixIcon: Icon(Icons.search),
                    isDense: true,
                  ),
                  textCapitalization: TextCapitalization.characters,
                  onSubmitted: (_) => _loadNSEAnnouncements(),
                ),
              ),
              const SizedBox(width: 12),
              ElevatedButton(
                onPressed: _nseLoading ? null : _loadNSEAnnouncements,
                child: _nseLoading
                    ? const SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: Colors.white,
                        ),
                      )
                    : const Text('Search'),
              ),
            ],
          ),
        ),

        if (_nseError != null)
          Padding(
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
                      _nseError!,
                      style: const TextStyle(color: AppTheme.errorColor),
                    ),
                  ),
                ],
              ),
            ),
          ),

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
                        'Enter a symbol and search\nto view announcements',
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
    );
  }

  Widget _buildBSETab() {
    return Column(
      children: [
        // Load button
        Padding(
          padding: const EdgeInsets.all(16),
          child: SizedBox(
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
                  : const Icon(Icons.download),
              label: Text(
                _bseLoading ? 'Loading...' : 'Load Today\'s BSE Announcements',
              ),
            ),
          ),
        ),

        if (_bseError != null)
          Padding(
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
                      _bseError!,
                      style: const TextStyle(color: AppTheme.errorColor),
                    ),
                  ),
                ],
              ),
            ),
          ),

        // Results
        Expanded(
          child: _bseAnnouncements.isEmpty
              ? Center(
                  child: Text(
                    'Tap the button to load announcements',
                    style: TextStyle(color: AppTheme.textSecondary),
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

        // Pagination
        if (_bseTotalPages > 1)
          Container(
            padding: const EdgeInsets.all(12),
            color: AppTheme.cardColor,
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                IconButton(
                  onPressed: _bsePage > 1
                      ? () => _loadBSEAnnouncements(page: _bsePage - 1)
                      : null,
                  icon: const Icon(Icons.chevron_left),
                ),
                Text(
                  'Page $_bsePage of $_bseTotalPages',
                  style: TextStyle(color: AppTheme.textSecondary),
                ),
                IconButton(
                  onPressed: _bsePage < _bseTotalPages
                      ? () => _loadBSEAnnouncements(page: _bsePage + 1)
                      : null,
                  icon: const Icon(Icons.chevron_right),
                ),
              ],
            ),
          ),
      ],
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
                Container(
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
              const Spacer(),
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
