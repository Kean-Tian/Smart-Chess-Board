/* Thin CLI adapter to the existing public native player API. No SQL here. */
#include "player_store.h"
#include <stdio.h>
#include <string.h>
#include <strings.h>

static int find_or_create(PlayerStore *store, const char *name, ScbPlayer *out) {
    int offset = 0, total = 0, count = 0;
    do {
        ScbPlayer rows[SCB_PLAYER_PAGE_SIZE];
        if(!player_store_page(store, offset, rows, &count, &total)) return 0;
        for(int i = 0; i < count; ++i) {
            if(strcasecmp(rows[i].name, name) == 0) {
                *out = rows[i];
                return 1;
            }
        }
        offset += count;
    } while(count && offset < total);
    return player_store_create(store, name) && player_store_selected(store, out);
}

int main(int argc, char **argv) {
    if(argc != 4 || !argv[1][0]) {
        fputs("Usage: fixture_players EXPLICIT_TEST_DB WHITE_NAME BLACK_NAME\n", stderr);
        return 2;
    }
    PlayerStore store;
    if(!player_store_open(&store, argv[1])) {
        fprintf(stderr, "%s\n", store.error);
        return 2;
    }
    ScbPlayer white, black;
    int ok = find_or_create(&store, argv[2], &white) &&
             find_or_create(&store, argv[3], &black);
    if(ok) printf("%lld %lld\n", (long long)white.id, (long long)black.id);
    else fprintf(stderr, "%s\n", store.error);
    player_store_close(&store);
    return ok ? 0 : 2;
}
