import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import '../../config/api_config.dart';
import '../../core/services/auth_service.dart';
import '../../shared/widgets/profile_menu.dart';
import 'video_player_screen.dart';

class LearnScreen extends StatefulWidget {
  const LearnScreen({super.key});

  @override
  State<LearnScreen> createState() => _LearnScreenState();
}

class _LearnScreenState extends State<LearnScreen> {
  final TextEditingController _searchController = TextEditingController();
  List<Map<String, dynamic>> _videos = [];
  bool _loading = true;
  bool _loadingMore = false;
  String _nextPageToken = '';
  String? _error;
  bool _isSearching = false;
  final ScrollController _scrollController = ScrollController();

  @override
  void initState() {
    super.initState();
    _fetchVideos();
    _scrollController.addListener(_onScroll);
  }

  @override
  void dispose() {
    _searchController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  void _onScroll() {
    if (_scrollController.position.pixels >=
            _scrollController.position.maxScrollExtent - 200 &&
        !_loadingMore &&
        _nextPageToken.isNotEmpty) {
      _loadMore();
    }
  }

  Future<void> _fetchVideos({String pageToken = ''}) async {
    if (pageToken.isEmpty) {
      setState(() {
        _loading = true;
        _error = null;
      });
    }

    try {
      final uri = Uri.parse(ApiConfig.learnVideos).replace(
        queryParameters: {
          if (pageToken.isNotEmpty) 'page_token': pageToken,
          'max_results': '10',
        },
      );
      final response = await http.get(uri).timeout(const Duration(seconds: 15));

      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        final videos = (data['videos'] as List? ?? [])
            .cast<Map<String, dynamic>>();
        setState(() {
          if (pageToken.isEmpty) {
            _videos = videos;
          } else {
            _videos.addAll(videos);
          }
          _nextPageToken = data['nextPageToken'] ?? '';
          _loading = false;
          _loadingMore = false;
          _isSearching = false;
        });
      } else {
        setState(() {
          _error = 'Failed to load videos';
          _loading = false;
          _loadingMore = false;
        });
      }
    } catch (e) {
      setState(() {
        _error = 'Network error';
        _loading = false;
        _loadingMore = false;
      });
    }
  }

  Future<void> _searchVideos(String query, {String pageToken = ''}) async {
    if (query.trim().isEmpty) {
      _fetchVideos();
      return;
    }

    if (pageToken.isEmpty) {
      setState(() {
        _loading = true;
        _error = null;
        _isSearching = true;
      });
    }

    try {
      final uri = Uri.parse(ApiConfig.learnSearch).replace(
        queryParameters: {
          'q': query,
          if (pageToken.isNotEmpty) 'page_token': pageToken,
          'max_results': '10',
        },
      );
      final response = await http.get(uri).timeout(const Duration(seconds: 15));

      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        final videos = (data['videos'] as List? ?? [])
            .cast<Map<String, dynamic>>();
        setState(() {
          if (pageToken.isEmpty) {
            _videos = videos;
          } else {
            _videos.addAll(videos);
          }
          _nextPageToken = data['nextPageToken'] ?? '';
          _loading = false;
          _loadingMore = false;
        });
      } else {
        setState(() {
          _error = 'Search failed';
          _loading = false;
          _loadingMore = false;
        });
      }
    } catch (e) {
      setState(() {
        _error = 'Network error';
        _loading = false;
        _loadingMore = false;
      });
    }
  }

  void _loadMore() {
    if (_nextPageToken.isEmpty || _loadingMore) return;
    setState(() => _loadingMore = true);
    if (_isSearching) {
      _searchVideos(_searchController.text, pageToken: _nextPageToken);
    } else {
      _fetchVideos(pageToken: _nextPageToken);
    }
  }

  String _formatViews(int views) {
    if (views >= 1000000) return '${(views / 1000000).toStringAsFixed(1)}M';
    if (views >= 1000) return '${(views / 1000).toStringAsFixed(1)}K';
    return views.toString();
  }

  String _formatDuration(String iso) {
    // Parse ISO 8601 duration like PT1H2M3S
    final match = RegExp(
      r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?',
    ).firstMatch(iso);
    if (match == null) return '';
    final h = int.tryParse(match.group(1) ?? '') ?? 0;
    final m = int.tryParse(match.group(2) ?? '') ?? 0;
    final s = int.tryParse(match.group(3) ?? '') ?? 0;
    if (h > 0) return '${h}h ${m}m';
    if (m > 0) return '${m}m ${s}s';
    return '${s}s';
  }

  String _timeAgo(String dateStr) {
    try {
      final date = DateTime.parse(dateStr);
      final diff = DateTime.now().difference(date);
      if (diff.inDays > 365) return '${(diff.inDays / 365).floor()}y ago';
      if (diff.inDays > 30) return '${(diff.inDays / 30).floor()}mo ago';
      if (diff.inDays > 0) return '${diff.inDays}d ago';
      if (diff.inHours > 0) return '${diff.inHours}h ago';
      return '${diff.inMinutes}m ago';
    } catch (_) {
      return '';
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text(
          'Learn',
          style: TextStyle(fontWeight: FontWeight.w700, fontSize: 20),
        ),
        actions: [
          ProfileMenu(authService: AuthService()),
        ],
        centerTitle: false,
        elevation: 0,
      ),
      body: Column(
        children: [
          // Search bar
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
            child: TextField(
              controller: _searchController,
              decoration: InputDecoration(
                hintText: 'Search videos...',
                prefixIcon: const Icon(Icons.search),
                suffixIcon: _searchController.text.isNotEmpty
                    ? IconButton(
                        icon: const Icon(Icons.clear),
                        onPressed: () {
                          _searchController.clear();
                          _fetchVideos();
                        },
                      )
                    : null,
                filled: true,
                fillColor: Theme.of(context).cardTheme.color,
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(14),
                  borderSide: BorderSide.none,
                ),
                contentPadding: const EdgeInsets.symmetric(vertical: 12),
              ),
              onChanged: (q) {
                setState(() {}); // Update suffix icon
              },
              onSubmitted: (q) => _searchVideos(q),
            ),
          ),

          // Content
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : _error != null
                ? Center(
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(
                          Icons.error_outline,
                          size: 48,
                          color: Theme.of(context).colorScheme.onSurfaceVariant,
                        ),
                        const SizedBox(height: 12),
                        Text(
                          _error!,
                          style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant),
                        ),
                        const SizedBox(height: 12),
                        ElevatedButton(
                          onPressed: () => _fetchVideos(),
                          child: const Text('Retry'),
                        ),
                      ],
                    ),
                  )
                : _videos.isEmpty
                ? Center(
                    child: Text(
                      _isSearching ? 'No videos found' : 'No videos available',
                      style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant),
                    ),
                  )
                : RefreshIndicator(
                    onRefresh: () => _isSearching
                        ? _searchVideos(_searchController.text)
                        : _fetchVideos(),
                    child: ListView.builder(
                      controller: _scrollController,
                      padding: const EdgeInsets.symmetric(horizontal: 16),
                      itemCount: _videos.length + (_loadingMore ? 1 : 0),
                      itemBuilder: (context, index) {
                        if (index == _videos.length) {
                          return const Padding(
                            padding: EdgeInsets.all(16),
                            child: Center(child: CircularProgressIndicator()),
                          );
                        }
                        return _buildVideoCard(_videos[index]);
                      },
                    ),
                  ),
          ),
        ],
      ),
    );
  }

  Widget _buildVideoCard(Map<String, dynamic> video) {
    final title = video['title'] ?? '';
    final thumbnail = video['thumbnail'] ?? '';
    final views = video['views'] as int? ?? 0;
    final duration = _formatDuration(video['duration'] ?? '');
    final timeAgo = _timeAgo(video['publishedAt'] ?? '');

    return GestureDetector(
      onTap: () {
        Navigator.push(
          context,
          MaterialPageRoute(
            builder: (_) => VideoPlayerScreen(
              videoId: video['videoId'] ?? '',
              title: title,
              description: video['description'] ?? '',
              views: views,
              publishedAt: video['publishedAt'] ?? '',
            ),
          ),
        );
      },
      child: Container(
        margin: const EdgeInsets.only(bottom: 16),
        decoration: BoxDecoration(
          color: Theme.of(context).cardTheme.color,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: Theme.of(context).dividerColor.withOpacity(0.1)),
        ),
        clipBehavior: Clip.antiAlias,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Thumbnail
            Stack(
              children: [
                AspectRatio(
                  aspectRatio: 16 / 9,
                  child: thumbnail.isNotEmpty
                      ? Image.network(
                          thumbnail,
                          fit: BoxFit.cover,
                          errorBuilder: (_, __, ___) => Container(
                            color: Colors.grey[900],
                            child: const Icon(
                              Icons.play_circle_outline,
                              size: 48,
                            ),
                          ),
                        )
                      : Container(
                          color: Colors.grey[900],
                          child: const Icon(
                            Icons.play_circle_outline,
                            size: 48,
                          ),
                        ),
                ),
                // Duration badge
                if (duration.isNotEmpty)
                  Positioned(
                    bottom: 8,
                    right: 8,
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 6,
                        vertical: 3,
                      ),
                      decoration: BoxDecoration(
                        color: Colors.black87,
                        borderRadius: BorderRadius.circular(4),
                      ),
                      child: Text(
                        duration,
                        style: const TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.w600,
                          color: Colors.white,
                        ),
                      ),
                    ),
                  ),
                // Play overlay
                Positioned.fill(
                  child: Center(
                    child: Container(
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(
                        color: Colors.black45,
                        shape: BoxShape.circle,
                      ),
                      child: const Icon(
                        Icons.play_arrow_rounded,
                        color: Colors.white,
                        size: 32,
                      ),
                    ),
                  ),
                ),
              ],
            ),
            // Info
            Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: const TextStyle(
                      fontWeight: FontWeight.w600,
                      fontSize: 14,
                      height: 1.3,
                    ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 6),
                  Row(
                    children: [
                      Icon(
                        Icons.visibility_outlined,
                        size: 14,
                        color: Theme.of(context).colorScheme.onSurfaceVariant,
                      ),
                      const SizedBox(width: 4),
                      Text(
                        '${_formatViews(views)} views',
                        style: TextStyle(
                          fontSize: 12,
                          color: Theme.of(context).colorScheme.onSurfaceVariant,
                        ),
                      ),
                      const SizedBox(width: 12),
                      Icon(
                        Icons.access_time,
                        size: 14,
                        color: Theme.of(context).colorScheme.onSurfaceVariant,
                      ),
                      const SizedBox(width: 4),
                      Text(
                        timeAgo,
                        style: TextStyle(
                          fontSize: 12,
                          color: Theme.of(context).colorScheme.onSurfaceVariant,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
