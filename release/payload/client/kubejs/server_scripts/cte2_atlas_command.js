// priority: 0
// Server-only administrative command: Mine and Slash 6.4.13 / Dungeon Realm 1.1.16.
ServerEvents.commandRegistry(function (event) {
    var Commands = event.commands;
    var Component = Java.loadClass('net.minecraft.network.chat.Component');
    var ServerPlayer = Java.loadClass('net.minecraft.server.level.ServerPlayer');
    var CompoundTag = Java.loadClass('net.minecraft.nbt.CompoundTag');
    var Gson = Java.loadClass('com.google.gson.Gson');
    var AtlasData = Java.loadClass('com.robertx22.mine_and_slash.saveclasses.atlas.AtlasData');
    var ExileDB = Java.loadClass('com.robertx22.mine_and_slash.database.registry.ExileDB');
    var DungeonDB = Java.loadClass('com.robertx22.dungeon_realm.database.DungeonDatabase');
    var PointsType = Java.loadClass('com.robertx22.mine_and_slash.database.data.game_balance_config.PlayerPointsType');
    var Load = Java.loadClass('com.robertx22.mine_and_slash.uncommon.datasaving.Load');
    var gson = new Gson();
    var BACKUPS = 'cte2_atlas_command_backups_v1';

    // KubeJS also converts JS strings to JsonElement. Select exact overloads so
    // fromJson(String, Class) cannot conflict with fromJson(JsonElement, Class).
    function encode(data) {
        return String(gson['toJson(java.lang.Object)'](data));
    }
    function decodeAtlas(json) {
        return gson['fromJson(java.lang.String,java.lang.Class)'](String(json), AtlasData);
    }

    function fail(source, text) {
        source.sendFailure(Component.literal('[CTE2 아틀라스] ' + text));
        return 0;
    }
    function success(source, text, broadcast) {
        source.sendSuccess(function () { return Component.literal('[CTE2 아틀라스] ' + text); }, broadcast);
    }
    function refresh(player, data) {
        data.cachedStats.ALLOCATED.setDirtyAndSync(player);
        data.playerDataSync.setDirtyAndSync(player);
        Load.Unit(player).setAllDirtyOnLoginEtc();
    }
    function backupLocation(player, data) {
        var persistent = player.getPersistentData();
        var persisted = persistent.getCompound('PlayerPersisted');
        var backups = persisted.getCompound(BACKUPS);
        return {
            // Atlas progress and bonus points are shared across character slots.
            key: 'last',
            get: function () { return backups.getCompound(this.key); },
            has: function () { return backups.contains(this.key); },
            put: function (backup) {
                backups.put(this.key, backup);
                persisted.put(BACKUPS, backups);
                persistent.put('PlayerPersisted', persisted);
            },
            remove: function () {
                backups.remove(this.key);
                persisted.put(BACKUPS, backups);
                persistent.put('PlayerPersisted', persisted);
            }
        };
    }
    function sameAtlas(left, right) {
        return left.completedNodes.equals(right.completedNodes)
            && left.unlockedNodes.equals(right.unlockedNodes)
            && left.pinnacleUnlocked === right.pinnacleUnlocked;
    }
    function nodesOnAtlas() {
        // Rhino intentionally hides transient fields, including CalcData.pointOf.
        // Match AtlasGridPoint's parsing rule using the public source CSV instead.
        // Like AtlasNodeLayout.mainCalcData(), use the first registered layout only.
        var layouts = ExileDB.AtlasNodeLayouts().getList();
        if (layouts.isEmpty()) throw new Error('아틀라스 레이아웃이 로드되지 않았습니다.');
        var cells = String(layouts.get(0).nodes).split(/[\n,]/);
        var registry = DungeonDB.AtlasNodes();
        var nodes = [];
        var seen = Object.create(null);
        for (var i = 0; i < cells.length; i++) {
            var id = cells[i].toLowerCase();
            // Empty cells, center markers and connectors are not atlas nodes.
            if (!seen[id] && registry.isRegistered(id)) {
                nodes.push(registry.get(id));
                seen[id] = true;
            }
        }
        if (nodes.length === 0) throw new Error('배치된 아틀라스 노드가 없습니다. 데이터 로드를 확인해 주세요.');
        return nodes;
    }

    function run(context, action) {
        var source = context.getSource();
        if (!source.hasPermission(2)) return fail(source, 'OP 권한(레벨 2 이상)이 필요합니다.');
        var player = source.getEntity();
        if (!(player instanceof ServerPlayer)) return fail(source, '게임 안의 플레이어가 실행해야 합니다.');

        var data = Load.player(player);
        var points = data.points.get(PointsType.ATLAS);
        var originalAtlas = data.atlas;
        var originalBonus = Number(points.getBonusPoints());
        var location = backupLocation(player, data);
        var previousBackup = location.has() ? location.get().copy() : null;
        var mutated = false;
        var wroteBackup = false;
        var message;
        try {
            if (action === 'restore') {
                if (!location.has()) return fail(source, '현재 플레이어의 실행 전 백업이 없습니다.');
                var backup = location.get();
                var expectedAtlas = decodeAtlas(backup.getString('atlas_after'));
                // Do not discard post-command point spending or unrelated point changes.
                if (!sameAtlas(data.atlas, expectedAtlas)
                    || Number(data.characters.current) !== backup.getInt('slot_before')
                    || encode(data.characters) !== String(backup.getString('characters_before'))
                    || Number(points.getBonusPoints()) !== backup.getInt('bonus_after')
                    || Number(points.getBonusCheatPoints()) !== backup.getInt('cheat_before')
                    || Number(points.reset_points) !== backup.getInt('reset_before')
                    || Number(PointsType.ATLAS.getPointsInUse(player)) !== backup.getInt('used_before')) {
                    return fail(source, '실행 후 진행도·포인트가 변경되어 안전하게 복원할 수 없습니다. 백업은 유지합니다. 새로 쓴 아틀라스 포인트는 먼저 회수해 주세요.');
                }
                var restored = decodeAtlas(backup.getString('atlas_before'));
                data.atlas = restored;
                mutated = true;
                points.giveBonusPoints(backup.getInt('bonus_before') - Number(points.getBonusPoints()));
                refresh(player, data);
                location.remove();
                message = '이 플레이어의 공유 아틀라스를 전체 완료 명령 실행 전 상태로 복원했습니다.';
            } else {
                var nodes = nodesOnAtlas();
                var completed = 0;
                var required = 0;
                var requiredDone = 0;
                for (var i = 0; i < nodes.length; i++) {
                    if (data.atlas.isCompleted(nodes[i].id)) completed++;
                    if (nodes[i].is_pinnacle_unlock) {
                        required++;
                        if (data.atlas.isCompleted(nodes[i].id)) requiredDone++;
                    }
                }
                if (action === 'status') {
                    success(source, 'v1.2 · 계정 공유 진행도 (현재 슬롯 ' + Number(data.characters.current) + ')'
                        + ': 완료 ' + completed + '/' + nodes.length
                        + ', 정점 조건 ' + requiredDone + '/' + required
                        + ', 정점 해금 ' + data.atlas.pinnacleUnlocked
                        + '. /cteatlas complete | /cteatlas restore', false);
                    return 1;
                }

                var beforeJson = encode(data.atlas);
                var nextAtlas = decodeAtlas(beforeJson);
                var added = 0;
                var reward = 0;
                // Unlock first, so graph ordering cannot skip a previously locked node.
                for (var j = 0; j < nodes.length; j++) nextAtlas.unlockedNodes.add(nodes[j].id);
                for (var k = 0; k < nodes.length; k++) {
                    if (nextAtlas.markCompleted(nodes[k])) {
                        added++;
                        reward += Number(nodes[k].atlas_points_reward);
                    }
                }
                if (required > 0) nextAtlas.pinnacleUnlocked = true;
                if (sameAtlas(nextAtlas, data.atlas)) {
                    success(source, '이미 전체 완료 상태입니다. 포인트를 중복 지급하지 않았습니다.', false);
                    return 1;
                }

                var snapshot = new CompoundTag();
                snapshot.putString('atlas_before', beforeJson);
                snapshot.putString('atlas_after', encode(nextAtlas));
                snapshot.putInt('bonus_before', originalBonus);
                snapshot.putInt('bonus_after', originalBonus + reward);
                snapshot.putInt('cheat_before', Number(points.getBonusCheatPoints()));
                snapshot.putInt('reset_before', Number(points.reset_points));
                snapshot.putInt('used_before', Number(PointsType.ATLAS.getPointsInUse(player)));
                snapshot.putInt('slot_before', Number(data.characters.current));
                snapshot.putString('characters_before', encode(data.characters));
                // Save per-world, per-player. Character guard prevents unsafe point rollback.
                location.put(snapshot);
                wroteBackup = true;
                if (String(location.get().getString('atlas_before')) !== beforeJson) {
                    throw new Error('진행도 백업 저장 검증에 실패했습니다.');
                }
                data.atlas = nextAtlas;
                mutated = true;
                if (reward !== 0) points.giveBonusPoints(reward);
                if (Number(points.getBonusPoints()) !== originalBonus + reward) {
                    throw new Error('아틀라스 포인트 저장 검증에 실패했습니다.');
                }
                refresh(player, data);
                message = '전체 ' + nodes.length + '개 완료. 새로 완료 ' + added
                    + '개, 미수령 노드 보상 +' + reward + '포인트, 정점 해금 '
                    + nextAtlas.pinnacleUnlocked + '. 복원: /cteatlas restore';
            }
        } catch (error) {
            try {
                if (mutated) {
                    data.atlas = originalAtlas;
                    points.giveBonusPoints(originalBonus - Number(points.getBonusPoints()));
                    refresh(player, data);
                }
                if (wroteBackup || action === 'restore') {
                    if (previousBackup !== null) location.put(previousBackup);
                    else location.remove();
                }
            } catch (rollbackError) {
                console.error('[CTE2 atlas rollback] ' + rollbackError);
                return fail(source, '복구 중 오류가 발생했습니다. 추가 실행을 멈추고 서버 로그를 확인해 주세요.');
            }
            console.error('[CTE2 atlas] ' + error);
            return fail(source, '실패하여 진행도와 포인트를 원상 복구했습니다. 서버 로그를 확인해 주세요.');
        }
        success(source, message, true);
        return 1;
    }

    event.register(Commands.literal('cteatlas')
        .requires(function (source) { return source.hasPermission(2); })
        .executes(function (context) { return run(context, 'status'); })
        .then(Commands.literal('complete').executes(function (context) { return run(context, 'complete'); }))
        .then(Commands.literal('restore').executes(function (context) { return run(context, 'restore'); })));
});
