// priority: 0
// Server-only, OP level 2. Mine and Slash 6.4.13 / KubeJS 2001.6.5.
// Changes the real quality key used by BaseStatsData, not display text.
ServerEvents.commandRegistry(function (event) {
    var Commands = event.commands;
    var IntegerArgument = Java.loadClass('com.mojang.brigadier.arguments.IntegerArgumentType');
    var Component = Java.loadClass('net.minecraft.network.chat.Component');
    var ServerPlayer = Java.loadClass('net.minecraft.server.level.ServerPlayer');
    var InteractionHand = Java.loadClass('net.minecraft.world.InteractionHand');
    var ExileStack = Java.loadClass('com.robertx22.mine_and_slash.itemstack.ExileStack');
    var StackKeys = Java.loadClass('com.robertx22.mine_and_slash.itemstack.StackKeys');
    var CustomItemData = Java.loadClass('com.robertx22.mine_and_slash.itemstack.CustomItemData');
    var Load = Java.loadClass('com.robertx22.mine_and_slash.uncommon.datasaving.Load');
    // Administrative safety limit, not the game's normal crafting limit.
    var MAX_QUALITY = 10000;

    function fail(source, message) {
        source.sendFailure(Component.literal('[CTE2 품질] ' + message));
        return 0;
    }

    function run(context, changeQuality) {
        var source = context.getSource();
        // Also guard here, independently of Brigadier visibility checks.
        if (!source.hasPermission(2)) {
            return fail(source, 'OP 권한(레벨 2 이상)이 필요합니다.');
        }
        var player = source.getEntity();
        if (!(player instanceof ServerPlayer)) {
            return fail(source, '게임 안의 플레이어가 실행해야 합니다.');
        }

        var original = player.getMainHandItem();
        if (original.isEmpty()) {
            return fail(source, '변경할 장비를 주 손에 들어 주세요.');
        }

        var committed = false;
        try {
            // ExileStack.of copies the stack, preserving all other item data.
            var copy = ExileStack.of(original);
            var gearPart = copy.get(StackKeys.GEAR);
            if (!gearPart.has() || !gearPart.get().isValidItem()) {
                return fail(source, '식별된 Mine and Slash 장비만 사용할 수 있습니다.');
            }
            var customPart = copy.get(StackKeys.CUSTOM);
            var custom = customPart.getOrCreate();
            var oldQuality = Number(custom.data.get(CustomItemData.KEYS.QUALITY));

            if (!changeQuality) {
                source.sendSuccess(function () {
                    return Component.literal('[CTE2 품질] 현재 품질: ' + oldQuality
                        + ' / 변경: /ctequality <0~' + MAX_QUALITY + '>');
                }, false);
                return 1;
            }

            var newQuality = IntegerArgument.getInteger(context, 'quality');
            // Only this key is edited. No gear generation, reroll or rarity change.
            // IntKey.add accepts an int, avoiding JS-number -> generic Object boxing.
            CustomItemData.KEYS.QUALITY.add(custom, newQuality - oldQuality);
            customPart.save();
            var savedQuality = Number(ExileStack.of(copy.getStack()).get(StackKeys.CUSTOM)
                .get().data.get(CustomItemData.KEYS.QUALITY));
            if (savedQuality !== Number(newQuality)) {
                return fail(source, '품질 저장 검증에 실패했습니다. 원본은 변경하지 않았습니다.');
            }

            player.setItemInHand(InteractionHand.MAIN_HAND, copy.getStack());
            committed = true;
            // Server inventory synchronization and the mod's normal stat refresh.
            player.getInventory().setChanged();
            player.inventoryMenu.broadcastChanges();
            Load.Unit(player).setAllDirtyOnLoginEtc();
        } catch (error) {
            if (committed) {
                player.setItemInHand(InteractionHand.MAIN_HAND, original);
                player.getInventory().setChanged();
                player.inventoryMenu.broadcastChanges();
                Load.Unit(player).setAllDirtyOnLoginEtc();
            }
            console.error('[CTE2 quality] ' + error);
            return fail(source, '변경에 실패했습니다. 원본 장비를 유지했습니다. 서버 로그를 확인해 주세요.');
        }

        source.sendSuccess(function () {
            return Component.literal('[CTE2 품질] 실제 품질 ' + oldQuality + ' → '
                + newQuality + '. 기본 능력치 재계산을 요청했습니다.');
        }, true);
        return 1;
    }

    event.register(Commands.literal('ctequality')
        .requires(function (source) { return source.hasPermission(2); })
        .executes(function (context) { return run(context, false); })
        .then(Commands.argument('quality', IntegerArgument.integer(0, MAX_QUALITY))
            .executes(function (context) { return run(context, true); })));
});
