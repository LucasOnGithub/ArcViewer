using System;
using System.Collections.Generic;
using System.Text;
using System.Text.RegularExpressions;
using Newtonsoft.Json;
using UnityEngine;

/// <summary>
/// Reads the pose-only JSON exported by Robo-Saber's generate.py:
/// { "gen3p": [[[x,y,z,qx,qy,qz,qw], ...three poses], ...], "song_hash": ..., "difficulty": ... }.
/// The three poses are head, left hand, right hand, sampled at 60 Hz in a Z-up coordinate system.
/// </summary>
public static class RoboSaberReplayDecoder
{
    private const float FramesPerSecond = 60f;
    private const float DefaultPlayerHeight = 1.5044f;

    private sealed class RoboSaberFile
    {
        public float[][][] gen3p;
        public string song_hash;
        public string difficulty;
    }

    private static bool IsFinite(float value) => !float.IsNaN(value) && !float.IsInfinity(value);

    private static PositionData ConvertPose(float[] pose, int frameIndex, string label)
    {
        if(pose == null || pose.Length != 7)
        {
            throw new FormatException($"Robo-Saber frame {frameIndex} has an invalid {label} pose (expected 7 numbers).");
        }

        for(int i = 0; i < pose.Length; i++)
        {
            if(!IsFinite(pose[i]))
            {
                throw new FormatException($"Robo-Saber frame {frameIndex} has a non-finite {label} pose.");
            }
        }

        // Inverse of Robo-Saber's beaty_common.pose_utils.unity_to_zup:
        // Z-up xyz -> Unity xyz: (-y, z, x)
        // Z-up xyzw -> Unity xyzw: (y, -z, -x, w)
        Vector3 position = new Vector3(-pose[1], pose[2], pose[0]);
        Quaternion rotation = new Quaternion(pose[4], -pose[5], -pose[3], pose[6]);
        float magnitudeSquared = rotation.x * rotation.x + rotation.y * rotation.y
            + rotation.z * rotation.z + rotation.w * rotation.w;
        if(magnitudeSquared < 0.000001f)
        {
            throw new FormatException($"Robo-Saber frame {frameIndex} has a zero {label} quaternion.");
        }

        return new PositionData
        {
            position = position,
            rotation = Quaternion.Normalize(rotation)
        };
    }

    public static Replay Decode(byte[] bytes)
    {
        if(bytes == null || bytes.Length == 0)
        {
            throw new FormatException("Robo-Saber replay JSON is empty.");
        }

        RoboSaberFile source;
        try
        {
            source = JsonConvert.DeserializeObject<RoboSaberFile>(Encoding.UTF8.GetString(bytes));
        }
        catch(JsonException error)
        {
            throw new FormatException("Unable to parse Robo-Saber replay JSON.", error);
        }

        if(source?.gen3p == null || source.gen3p.Length < 2)
        {
            throw new FormatException("Robo-Saber replay must contain at least two gen3p frames.");
        }

        string mapHash = source.song_hash ?? "";
        if(!Regex.IsMatch(mapHash, @"^[0-9a-fA-F]{40}$"))
        {
            // A local, unpublished map has no BeatSaver SHA-1 hash; trigger the
            // existing manual map selection prompt rather than a bad online lookup.
            mapHash = "";
        }

        string difficulty = source.difficulty ?? "ExpertPlus";
        if(difficulty != "Easy" && difficulty != "Normal" && difficulty != "Hard"
            && difficulty != "Expert" && difficulty != "ExpertPlus")
        {
            throw new FormatException($"Unsupported Robo-Saber difficulty: {difficulty}");
        }

        Replay replay = new Replay();
        replay.info = new ReplayInfo
        {
            version = "Robo-Saber JSON",
            gameVersion = "",
            timestamp = "",
            playerID = "",
            playerName = "Robo-Saber",
            platform = "generated",
            hash = mapHash.ToUpperInvariant(),
            songName = "Robo-Saber Generated Replay",
            mapper = "",
            difficulty = difficulty,
            score = 0,
            mode = "Standard",
            environment = "",
            modifiers = "",
            jumpDistance = 0f,
            leftHanded = false,
            height = DefaultPlayerHeight,
            speed = 1f,
            isRoboSaber = true
        };

        List<Frame> frames = replay.frames;
        for(int i = 0; i < source.gen3p.Length; i++)
        {
            float[][] frame = source.gen3p[i];
            if(frame == null || frame.Length != 3)
            {
                throw new FormatException($"Robo-Saber frame {i} must have head, left hand, and right hand poses.");
            }

            frames.Add(new Frame
            {
                time = i / FramesPerSecond,
                fps = (int)FramesPerSecond,
                head = ConvertPose(frame[0], i, "head"),
                leftHand = ConvertPose(frame[1], i, "left hand"),
                rightHand = ConvertPose(frame[2], i, "right hand")
            });
        }

        // Robo-Saber exports poses but not beat-event results. We intentionally
        // leave notes/walls empty rather than inventing scores, hits, or misses.
        return replay;
    }
}
