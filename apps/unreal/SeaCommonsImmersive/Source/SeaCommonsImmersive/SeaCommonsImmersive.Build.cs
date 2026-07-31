using UnrealBuildTool;

public class SeaCommonsImmersive : ModuleRules
{
    public SeaCommonsImmersive(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

        PublicDependencyModuleNames.AddRange(new[]
        {
            "Core",
            "CoreUObject",
            "CinematicCamera",
            "Engine",
            "InputCore",
            "Json",
            "JsonUtilities",
            "Water",
            "PixelStreaming"
        });
    }
}
